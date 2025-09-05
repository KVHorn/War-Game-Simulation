#!/usr/bin/env python3
# =============================================================================
# File             : main.py
# Project          : Seek and Destroy Board Game
# Description      : This is the program for the board game Seek and Destroy 
#                   currently in developement. This code will run to keep track of 
#                   of all user's resources and resource output/income levels,
#                   held territories, army units and their locations, 
#                   research and developement levels, etc. Everything a player will need
#                   to track will be done so through this program.
#                   This program will also be responsible for displaying this information on
#                   each player's individual hand held screen as well as the game keeper's 
#                   master screen.
#
# Author           : Kyle Horn
# Created          : 8-13-2025
# Last Updated     : 8-13-2025
# Version          : 1.0
#
# Python           :
# Dependencies     :
# License          :
#
# Usage            :
#
#
# Notes            :
#     - 
#     -
#
#
#
# Ideas:
#   -Create a website where users 'login' with a game code and user name/password. 
#       -This would allow multiple different games to be played and saved for different groups of people.
#       - This would also allow players to use any device they want to view their game progress information
#
# 
#
#
#
#
#
#
# GAME OVERVIEW AND DESCRIPTION:
#
#
#
#
# IDEAS:
#   - Once a user has reached the highest research level in military tech, mining, and science, they 
#   will be able to develope/build this bomb.
#   This bomb is strong enough to completely destroy a target planet or moon chosen/targeted by the player.
#       - The core of this bomb is created with the core of a planet.
#       - In order to create this bomb, a player must choose a planet they currently control to sacrifice.
#           - Once "sacrificed" a planet and all units currently located on it are destroyed
#   
#   Name idea: 
#       1. Null Star or Void Star                    <- best idea so far **************** GO WITH THIS**********************
#   
#
# =============================================================================






"""Board Game Profiles CLI (SQLite-backed).

A CLI to create/manage player profiles and start new game sessions with
randomized turn order and unique color assignments when possible.

Examples:
    $ python main.py add kyle --name "Kyle H." --email kyle@example.com --color blue
    $ python main.py list
    $ python main.py show kyle
    $ python main.py update kyle --color red --timer 60 --pref theme=dark
    $ python main.py record kyle --result win
    $ python main.py new-game kyle alex sam --colors red,blue,green --seed 42
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple

# -----------------------------------------------------------------------------#
# Defaults
# -----------------------------------------------------------------------------#

DEFAULT_DB = Path("profiles.sqlite3")
DEFAULT_COLORS = ["red", "blue", "green", "yellow", "purple", "orange", "black", "white"]


# -----------------------------------------------------------------------------#
# Utilities / Data Model
# -----------------------------------------------------------------------------#

def _utc_now_iso() -> str:
    """Return the current UTC time as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


@dataclass
class PlayerProfile:
    """Container for a player's profile, stats, and preferences.

    Attributes:
        username: Unique key for the player.
        display_name: Human-friendly name.
        email: Optional email address.
        favorite_color: Preferred color/piece.
        avatar: Optional avatar path/URL/emoji.
        created_at: Creation timestamp (UTC, ISO-8601).
        updated_at: Last update timestamp (UTC, ISO-8601).
        stats: Mapping with keys ``games``, ``wins``, ``losses``, ``draws``.
        preferences: Arbitrary key/value settings.
    """

    username: str
    display_name: str
    email: Optional[str]
    favorite_color: Optional[str]
    avatar: Optional[str]
    created_at: str
    updated_at: str
    stats: Dict[str, int]
    preferences: Dict[str, Any]


def get_conn(path: Path) -> sqlite3.Connection:
    """Return a SQLite connection with sensible defaults.

    Args:
        path: Path to the SQLite database file.

    Returns:
        A configured :class:`sqlite3.Connection`.
    """
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Create tables if they do not already exist.

    This function is idempotent and safe to call on every startup.
    """
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS players (
            username       TEXT PRIMARY KEY,
            display_name   TEXT NOT NULL,
            email          TEXT,
            favorite_color TEXT,
            avatar         TEXT,
            created_at     TEXT NOT NULL,
            updated_at     TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS stats (
            username TEXT PRIMARY KEY
                     REFERENCES players(username) ON DELETE CASCADE,
            games    INTEGER NOT NULL DEFAULT 0,
            wins     INTEGER NOT NULL DEFAULT 0,
            losses   INTEGER NOT NULL DEFAULT 0,
            draws    INTEGER NOT NULL DEFAULT 0
        );

        CREATE TABLE IF NOT EXISTS preferences (
            username TEXT NOT NULL
                     REFERENCES players(username) ON DELETE CASCADE,
            key      TEXT NOT NULL,
            value    TEXT,
            PRIMARY KEY (username, key)
        );

        CREATE TABLE IF NOT EXISTS sessions (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            seed       INTEGER
        );

        CREATE TABLE IF NOT EXISTS session_players (
            session_id INTEGER NOT NULL
                       REFERENCES sessions(id) ON DELETE CASCADE,
            position   INTEGER NOT NULL,
            username   TEXT NOT NULL
                       REFERENCES players(username),
            color      TEXT NOT NULL,
            PRIMARY KEY (session_id, position)
        );
        """
    )
    conn.commit()


# -----------------------------------------------------------------------------#
# Storage Layer
# -----------------------------------------------------------------------------#

class ProfileStore:
    """Repository for player profiles backed by SQLite."""

    def __init__(self, db_path: Path = DEFAULT_DB) -> None:
        """Initialize the store and ensure the database schema exists."""
        self.db_path = db_path
        self.conn = get_conn(db_path)
        ensure_schema(self.conn)

    # --- Creation / Retrieval -------------------------------------------------

    def add(self, username: str, display_name: str,
            email: Optional[str], favorite_color: Optional[str]) -> None:
        """Create a player and initialize stats.

        Args:
            username: Unique username.
            display_name: Friendly name (defaults handled by caller).
            email: Optional email.
            favorite_color: Optional preferred color.

        Raises:
            ValueError: If the username already exists.
        """
        now = _utc_now_iso()
        try:
            with self.conn:
                self.conn.execute(
                    "INSERT INTO players (username, display_name, email, favorite_color, avatar, created_at, updated_at) "
                    "VALUES (?, ?, ?, ?, NULL, ?, ?)",
                    (username, display_name, email, favorite_color, now, now),
                )
                self.conn.execute(
                    "INSERT INTO stats (username, games, wins, losses, draws) VALUES (?, 0, 0, 0, 0)",
                    (username,),
                )
        except sqlite3.IntegrityError as e:
            raise ValueError(f"username '{username}' already exists") from e

    def get(self, username: str) -> PlayerProfile:
        """Return a full :class:`PlayerProfile` record by username.

        Args:
            username: Profile key.

        Raises:
            ValueError: If the username does not exist.
        """
        cur = self.conn.execute(
            "SELECT * FROM players WHERE username = ?",
            (username,),
        )
        prow = cur.fetchone()
        if prow is None:
            raise ValueError(f"username '{username}' not found")

        srow = self.conn.execute(
            "SELECT games, wins, losses, draws FROM stats WHERE username = ?",
            (username,),
        ).fetchone()
        prefs = {
            r["key"]: r["value"]
            for r in self.conn.execute(
                "SELECT key, value FROM preferences WHERE username = ?",
                (username,),
            ).fetchall()
        }
        return PlayerProfile(
            username=prow["username"],
            display_name=prow["display_name"],
            email=prow["email"],
            favorite_color=prow["favorite_color"],
            avatar=prow["avatar"],
            created_at=prow["created_at"],
            updated_at=prow["updated_at"],
            stats={"games": srow["games"], "wins": srow["wins"], "losses": srow["losses"], "draws": srow["draws"]},
            preferences=prefs,
        )

    def all(self) -> Iterable[sqlite3.Row]:
        """Yield all players joined with stats for listing."""
        return self.conn.execute(
            """
            SELECT p.username, p.display_name, p.email, p.favorite_color,
                   s.games, s.wins, s.losses, s.draws
            FROM players AS p
            JOIN stats   AS s USING (username)
            ORDER BY p.username COLLATE NOCASE
            """
        )

    # --- Mutation -------------------------------------------------------------

    def update(self, username: str, *, display_name: Optional[str] = None,
               email: Optional[str] = None, favorite_color: Optional[str] = None,
               preferences: Optional[Dict[str, Any]] = None) -> PlayerProfile:
        """Update profile fields and preferences.

        Args:
            username: Profile key.
            display_name: Optional new display name.
            email: Optional new email.
            favorite_color: Optional new favorite color.
            preferences: Optional mapping to upsert into preferences.

        Returns:
            The updated profile.
        """
        # Ensure exists
        _ = self.get(username)

        fields: List[Tuple[str, Any]] = []
        if display_name is not None:
            fields.append(("display_name", display_name))
        if email is not None:
            fields.append(("email", email))
        if favorite_color is not None:
            fields.append(("favorite_color", favorite_color))
        if fields:
            set_clause = ", ".join(f"{k} = ?" for k, _ in fields) + ", updated_at = ?"
            params = [v for _, v in fields] + [_utc_now_iso(), username]
            with self.conn:
                self.conn.execute(f"UPDATE players SET {set_clause} WHERE username = ?", params)

        if preferences:
            with self.conn:
                for k, v in preferences.items():
                    self.conn.execute(
                        "INSERT INTO preferences (username, key, value) VALUES (?, ?, ?) "
                        "ON CONFLICT(username, key) DO UPDATE SET value = excluded.value",
                        (username, str(k), None if v is None else str(v)),
                    )
        return self.get(username)

    def delete(self, username: str) -> None:
        """Delete a player and associated stats/preferences.

        Args:
            username: Profile key.

        Raises:
            ValueError: If the username does not exist.
        """
        # Ensure exists
        _ = self.get(username)
        with self.conn:
            self.conn.execute("DELETE FROM players WHERE username = ?", (username,))

    def record_result(self, username: str, result: str) -> PlayerProfile:
        """Increment stats for a completed game.

        Args:
            username: Profile key.
            result: One of ``'win'``, ``'loss'``, or ``'draw'``.

        Returns:
            The updated profile.
        """
        key = {"win": "wins", "loss": "losses", "draw": "draws"}[result]
        with self.conn:
            self.conn.execute("UPDATE stats SET games = games + 1, {} = {} + 1 WHERE username = ?".format(key, key), (username,))
            self.conn.execute("UPDATE players SET updated_at = ? WHERE username = ?", (_utc_now_iso(), username))
        return self.get(username)

    # --- Sessions -------------------------------------------------------------

    def create_session(self, players_ordered: List[str], colors: Dict[str, str], seed: Optional[int]) -> int:
        """Create a session row and associated players in order.

        Args:
            players_ordered: Usernames in turn order.
            colors: Mapping of username to assigned color.
            seed: Optional random seed (stored for reproducibility).

        Returns:
            The new session id.
        """
        with self.conn:
            cur = self.conn.execute(
                "INSERT INTO sessions (created_at, seed) VALUES (?, ?)",
                (_utc_now_iso(), seed),
            )
            session_id = cur.lastrowid
            for pos, uname in enumerate(players_ordered, start=1):
                self.conn.execute(
                    "INSERT INTO session_players (session_id, position, username, color) "
                    "VALUES (?, ?, ?, ?)",
                    (session_id, pos, uname, colors[uname]),
                )
        return int(session_id)


# -----------------------------------------------------------------------------#
# Business Logic
# -----------------------------------------------------------------------------#

USERNAME_RE = re.compile(r"^[a-zA-Z0-9_-]{2,32}$")


def validate_username(username: str) -> str:
    """Validate a CLI username and return it unchanged.

    Raises:
        argparse.ArgumentTypeError: If invalid.
    """
    if not USERNAME_RE.match(username):
        raise argparse.ArgumentTypeError(
            "Username must be 2–32 chars: letters, numbers, underscore, hyphen."
        )
    return username


def parse_key_value(s: str) -> Tuple[str, str]:
    """Parse ``key=value`` or ``key:value`` and return a tuple."""
    if "=" in s:
        k, v = s.split("=", 1)
    elif ":" in s:
        k, v = s.split(":", 1)
    else:
        raise argparse.ArgumentTypeError("Use key=value or key:value format.")
    k, v = k.strip(), v.strip()
    if not k:
        raise argparse.ArgumentTypeError("Preference key cannot be empty.")
    return k, v


def assign_colors(usernames: List[str], store: ProfileStore, available: List[str]) -> Dict[str, str]:
    """Assign colors to players, honoring favorites and avoiding conflicts.

    Players receive their favorite color if available and unused; remaining
    players are assigned from the available pool; duplicates are allowed only
    when there are more players than colors.

    Returns:
        Mapping of username -> assigned color (lowercase).
    """
    available_norm = [c.lower() for c in available]
    taken: Dict[str, str] = {}

    # Give favorites where possible.
    for u in usernames:
        fav = (store.get(u).favorite_color or "").lower().strip()
        if fav and fav in available_norm and fav not in taken.values():
            taken[u] = fav

    # Assign remaining unique colors.
    for u in usernames:
        if u in taken:
            continue
        for c in available_norm:
            if c not in taken.values():
                taken[u] = c
                break

    # Allow duplicates if we ran out.
    for u in usernames:
        if u not in taken:
            taken[u] = available_norm[(len(taken)) % len(available_norm)]

    return taken


# -----------------------------------------------------------------------------#
# CLI Commands
# -----------------------------------------------------------------------------#

def cmd_add(args: argparse.Namespace) -> None:
    """Create a new player profile (supports interactive prompts)."""
    store = ProfileStore(args.db)
    if args.interactive:
        print("Creating profile interactively. Press Enter to skip a field.")
        name = input(f"Display name [{args.name or args.username}]: ").strip() or args.name or args.username
        email = input(f"Email [{args.email or ''}]: ").strip() or args.email
        color = input(f"Favorite color [{args.color or ''}]: ").strip() or args.color
    else:
        name, email, color = args.name or args.username, args.email, args.color
    store.add(args.username, name, email, color)
    print(f"✔ Created profile '{args.username}'")


def cmd_list(args: argparse.Namespace) -> None:
    """List all profiles in a compact table."""
    store = ProfileStore(args.db)
    rows = list(store.all())
    if not rows:
        print("(no profiles yet)")
        return
    print(f"{'username':<18} {'name':<22} {'wins':>4} {'loss':>4} {'draw':>4} {'games':>5} {'fav_color':<10}")
    print("-" * 70)
    for r in rows:
        print(f"{r['username']:<18} {r['display_name']:<22} {r['wins']:>4} {r['losses']:>4} {r['draws']:>4} {r['games']:>5} {str(r['favorite_color'] or '-'):<10}")


def cmd_show(args: argparse.Namespace) -> None:
    """Show a profile as pretty-printed JSON (including stats & preferences)."""
    store = ProfileStore(args.db)
    prof = store.get(args.username)
    print(json.dumps(asdict(prof), indent=2))


def cmd_update(args: argparse.Namespace) -> None:
    """Update profile fields and upsert preferences."""
    store = ProfileStore(args.db)
    extras: Dict[str, Any] = {}

    # Map explicit flags to preferences
    if args.piece is not None:
        extras["piece"] = args.piece
    if args.timer is not None:
        extras["turn_timer"] = args.timer

    # Parse repeatable --pref KEY=VALUE
    if args.pref:
        for kv in args.pref:
            k, v = parse_key_value(kv)
            extras[k] = v

    prof = store.update(
        args.username,
        display_name=args.name,
        email=args.email,
        favorite_color=args.color,
        preferences=extras if extras else None,
    )
    print(f"✔ Updated '{args.username}' at {prof.updated_at}")


def cmd_delete(args: argparse.Namespace) -> None:
    """Delete a profile by username."""
    store = ProfileStore(args.db)
    store.delete(args.username)
    print(f"✔ Deleted profile '{args.username}'")


def cmd_record(args: argparse.Namespace) -> None:
    """Record a single game outcome (win/loss/draw) for a user."""
    store = ProfileStore(args.db)
    prof = store.record_result(args.username, args.result)
    s = prof.stats
    print(f"✔ Recorded {args.result} for '{args.username}'. "
          f"Now {s['wins']}W/{s['losses']}L/{s['draws']}D across {s['games']} games.")


def cmd_new_game(args: argparse.Namespace) -> None:
    """Create a new game session with randomized order and color assignments."""
    store = ProfileStore(args.db)

    # Validate all players exist
    for u in args.usernames:
        store.get(u)

    if args.seed is not None:
        random.seed(args.seed)

    order = args.usernames[:]
    random.shuffle(order)

    colors_list = [c.strip() for c in (args.colors.split(",") if args.colors else DEFAULT_COLORS) if c.strip()]
    colors = assign_colors(order, store, colors_list)

    session_id = store.create_session(order, colors, args.seed)

    print(f"✔ New game session #{session_id}")
    print("Turn order:")
    for idx, u in enumerate(order, start=1):
        prof = store.get(u)
        print(f"  {idx}. {prof.display_name} (@{u}) — {colors[u]}")


# -----------------------------------------------------------------------------#
# CLI Wiring
# -----------------------------------------------------------------------------#

def build_parser() -> argparse.ArgumentParser:
    """Construct and return the top-level argparse parser."""
    p = argparse.ArgumentParser(description="Board Game Profiles CLI (SQLite)")
    p.add_argument("--db", type=Path, default=DEFAULT_DB, help="Path to SQLite database file")
    sub = p.add_subparsers(dest="cmd", required=True)

    # add
    s = sub.add_parser("add", help="Create a new player profile")
    s.add_argument("username", type=validate_username)
    s.add_argument("--name", help="Display name")
    s.add_argument("--email", help="Email")
    s.add_argument("--color", help="Favorite color / piece")
    s.add_argument("--interactive", "-i", action="store_true", help="Prompt for fields")
    s.set_defaults(func=cmd_add)

    # list
    s = sub.add_parser("list", help="List all profiles")
    s.set_defaults(func=cmd_list)

    # show
    s = sub.add_parser("show", help="Show a profile as JSON")
    s.add_argument("username", type=validate_username)
    s.set_defaults(func=cmd_show)

    # update
    s = sub.add_parser("update", help="Update profile fields")
    s.add_argument("username", type=validate_username)
    s.add_argument("--name", help="Display name")
    s.add_argument("--email", help="Email")
    s.add_argument("--color", help="Favorite color / piece")
    s.add_argument("--piece", help="Preferred piece name/type")
    s.add_argument("--timer", type=int, help="Turn timer in seconds")
    s.add_argument("--pref", action="append", metavar="KEY=VALUE",
                   help="Additional preference (repeatable). Example: --pref theme=dark")
    s.set_defaults(func=cmd_update)

    # delete
    s = sub.add_parser("delete", help="Delete a profile")
    s.add_argument("username", type=validate_username)
    s.set_defaults(func=cmd_delete)

    # record
    s = sub.add_parser("record", help="Record a game result for a user")
    s.add_argument("username", type=validate_username)
    s.add_argument("--result", choices=("win", "loss", "draw"), required=True)
    s.set_defaults(func=cmd_record)

    # new-game
    s = sub.add_parser("new-game", help="Create a new game session with order & colors")
    s.add_argument("usernames", nargs="+", type=validate_username, help="Players (existing usernames)")
    s.add_argument("--colors", help="Comma-separated list of allowed colors")
    s.add_argument("--seed", type=int, help="Optional RNG seed for reproducible order")
    s.set_defaults(func=cmd_new_game)

    return p


def main(argv: Optional[List[str]] = None) -> None:
    """Parse command-line arguments and dispatch to subcommands."""
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
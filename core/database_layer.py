"""
database_layer.py
-----------------
All SQLite reads and writes for FocusGuard.
No other module touches the .db file directly.

Database location:
  Windows : %APPDATA%\\focusguard\\focusguard.db
  macOS   : ~/Library/Application Support/focusguard/focusguard.db
"""

from __future__ import annotations

import json
import logging
import os
import platform
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from core.event_types import GazeSignal, SessionRecord, SessionTier

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# User data directory resolution
# ---------------------------------------------------------------------------

def get_user_data_dir() -> Path:
    """Return the platform-appropriate user data directory for FocusGuard."""
    system = platform.system()
    if system == "Windows":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif system == "Darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        # Linux fallback (not a target platform but useful for dev)
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))

    data_dir = base / "focusguard"
    data_dir.mkdir(parents=True, exist_ok=True)
    return data_dir


# ---------------------------------------------------------------------------
# DatabaseLayer
# ---------------------------------------------------------------------------

class DatabaseLayer:
    """
    Thin wrapper around sqlite3 for FocusGuard session storage.

    Usage:
        db = DatabaseLayer()
        db.write_session(record)
        sessions = db.get_sessions_for_date("2024-11-15")
    """

    def __init__(self, db_path: Optional[Path] = None) -> None:
        if db_path is None:
            db_path = get_user_data_dir() / "focusguard.db"
        self.db_path = db_path.resolve()
        self._conn: Optional[sqlite3.Connection] = None
        self._connect()
        self._create_schema()
        logger.info("DatabaseLayer initialised at %s", self.db_path)

    # ------------------------------------------------------------------
    # Connection management
    # ------------------------------------------------------------------

    def _connect(self) -> None:
        """Open the SQLite connection with WAL mode enabled."""
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,   # accessed from multiple threads
            isolation_level=None,      # autocommit; we manage transactions manually
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")

    def close(self) -> None:
        """Close the database connection gracefully."""
        if self._conn:
            self._conn.close()
            self._conn = None
            logger.info("DatabaseLayer connection closed")

    # ------------------------------------------------------------------
    # Schema creation
    # ------------------------------------------------------------------

    def _create_schema(self) -> None:
        """Create all tables if they don't already exist."""
        assert self._conn is not None

        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS sessions (
                id                INTEGER PRIMARY KEY AUTOINCREMENT,
                started_at        TEXT    NOT NULL,
                ended_at          TEXT    NOT NULL,
                duration_seconds  INTEGER NOT NULL,
                site              TEXT    NOT NULL,
                app_name          TEXT    NOT NULL,
                tier              TEXT    NOT NULL,
                signals_triggered TEXT    NOT NULL,
                gaze_status       TEXT    NOT NULL
            );

            CREATE TABLE IF NOT EXISTS sites (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                domain      TEXT    NOT NULL UNIQUE,
                category    TEXT    NOT NULL DEFAULT 'custom',
                date_added  TEXT    NOT NULL,
                enabled     INTEGER NOT NULL DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS config (
                key        TEXT NOT NULL,
                value      TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                PRIMARY KEY (key)
            );

            CREATE TABLE IF NOT EXISTS daily_summaries (
                date                      TEXT    PRIMARY KEY,
                confirmed_count           INTEGER NOT NULL DEFAULT 0,
                confirmed_duration_secs   INTEGER NOT NULL DEFAULT 0,
                unconfirmed_count         INTEGER NOT NULL DEFAULT 0,
                unconfirmed_duration_secs INTEGER NOT NULL DEFAULT 0,
                top_sites                 TEXT
            );
        """)
        logger.debug("Schema verified / created")

    # ------------------------------------------------------------------
    # Session writes
    # ------------------------------------------------------------------

    def write_session(self, session: SessionRecord) -> None:
        """
        Persist a completed SessionRecord to the sessions table and
        update the daily_summaries aggregate row.
        """
        assert self._conn is not None

        started_str = session.started_at.strftime("%Y-%m-%dT%H:%M:%SZ")
        ended_str = session.ended_at.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Convert the session start to the local timezone to determine the local calendar date
        local_start = session.started_at.astimezone()
        local_date_str = local_start.strftime("%Y-%m-%d")

        try:
            with self._conn:  # transaction
                self._conn.execute(
                    """
                    INSERT INTO sessions
                        (started_at, ended_at, duration_seconds, site, app_name,
                         tier, signals_triggered, gaze_status)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        started_str,
                        ended_str,
                        session.duration_seconds,
                        session.site,
                        session.app_name,
                        session.tier.value,
                        session.signals_triggered_json(),
                        session.gaze_status.value,
                    ),
                )
                self._update_daily_summary(local_date_str, session)

            logger.info(
                "Session written: %s | %s | %ds | %s (local date: %s)",
                session.tier.value,
                session.site,
                session.duration_seconds,
                started_str,
                local_date_str,
            )
        except sqlite3.Error as exc:
            logger.error("Failed to write session: %s", exc)
            raise

    def _update_daily_summary(
        self, date_str: str, session: SessionRecord
    ) -> None:
        """Upsert the daily_summaries row for the given date."""
        assert self._conn is not None

        # Fetch existing row (if any)
        row = self._conn.execute(
            "SELECT * FROM daily_summaries WHERE date = ?", (date_str,)
        ).fetchone()

        if row is None:
            confirmed_count = 0
            confirmed_secs = 0
            unconfirmed_count = 0
            unconfirmed_secs = 0
            top_sites_data: list = []
        else:
            confirmed_count = row["confirmed_count"]
            confirmed_secs = row["confirmed_duration_secs"]
            unconfirmed_count = row["unconfirmed_count"]
            unconfirmed_secs = row["unconfirmed_duration_secs"]
            top_sites_data = json.loads(row["top_sites"] or "[]")

        # Update counters
        if session.tier == SessionTier.CONFIRMED:
            confirmed_count += 1
            confirmed_secs += session.duration_seconds
        else:
            unconfirmed_count += 1
            unconfirmed_secs += session.duration_seconds

        # Update top_sites list
        site_entry = next(
            (s for s in top_sites_data if s["site"] == session.site), None
        )
        if site_entry:
            site_entry["duration_secs"] += session.duration_seconds
        else:
            top_sites_data.append(
                {"site": session.site, "duration_secs": session.duration_seconds}
            )
        top_sites_data.sort(key=lambda s: s["duration_secs"], reverse=True)

        self._conn.execute(
            """
            INSERT INTO daily_summaries
                (date, confirmed_count, confirmed_duration_secs,
                 unconfirmed_count, unconfirmed_duration_secs, top_sites)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(date) DO UPDATE SET
                confirmed_count           = excluded.confirmed_count,
                confirmed_duration_secs   = excluded.confirmed_duration_secs,
                unconfirmed_count         = excluded.unconfirmed_count,
                unconfirmed_duration_secs = excluded.unconfirmed_duration_secs,
                top_sites                 = excluded.top_sites
            """,
            (
                date_str,
                confirmed_count,
                confirmed_secs,
                unconfirmed_count,
                unconfirmed_secs,
                json.dumps(top_sites_data),
            ),
        )

    # ------------------------------------------------------------------
    # Config heartbeat (crash recovery)
    # ------------------------------------------------------------------

    def write_heartbeat(self) -> None:
        """Write a heartbeat timestamp to the config table every ~30s."""
        assert self._conn is not None
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with self._conn:
                self._conn.execute(
                    """
                    INSERT INTO config (key, value, updated_at)
                    VALUES ('last_heartbeat', ?, ?)
                    ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                                   updated_at = excluded.updated_at
                    """,
                    (now, now),
                )
        except sqlite3.Error as exc:
            logger.warning("Heartbeat write failed: %s", exc)

    def write_config_snapshot(self, config: dict) -> None:
        """Snapshot the full config dict into the config table at startup."""
        assert self._conn is not None
        now = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        try:
            with self._conn:
                for key, value in config.items():
                    self._conn.execute(
                        """
                        INSERT INTO config (key, value, updated_at)
                        VALUES (?, ?, ?)
                        ON CONFLICT(key) DO UPDATE SET value = excluded.value,
                                                       updated_at = excluded.updated_at
                        """,
                        (key, json.dumps(value), now),
                    )
        except sqlite3.Error as exc:
            logger.warning("Config snapshot write failed: %s", exc)

    # ------------------------------------------------------------------
    # Reads
    # ------------------------------------------------------------------

    def get_sessions_for_date(self, date_str: str) -> list[dict]:
        """Return all session rows for a given YYYY-MM-DD date string."""
        assert self._conn is not None
        try:
            # Parse the local date string
            local_date = datetime.strptime(date_str, "%Y-%m-%d")
            # Calculate start and end datetimes of the local day, localized to the system timezone
            local_start = datetime.combine(local_date, datetime.min.time()).astimezone()
            local_end = datetime.combine(local_date, datetime.max.time()).astimezone()

            # Convert to UTC ISO format strings to match the database timestamps
            start_utc = local_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            end_utc = local_end.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

            rows = self._conn.execute(
                """
                SELECT * FROM sessions
                WHERE started_at >= ? AND started_at <= ?
                ORDER BY started_at
                """,
                (start_utc, end_utc),
            ).fetchall()
        except ValueError:
            # Fallback to simple matching if date parsing fails
            rows = self._conn.execute(
                "SELECT * FROM sessions WHERE started_at LIKE ? ORDER BY started_at",
                (f"{date_str}%",),
            ).fetchall()

        return [dict(r) for r in rows]

    def get_daily_summary(self, date_str: str) -> Optional[dict]:
        """Return the daily_summaries row for a given date, or None."""
        assert self._conn is not None
        row = self._conn.execute(
            "SELECT * FROM daily_summaries WHERE date = ?", (date_str,)
        ).fetchone()
        return dict(row) if row else None

    def get_weekly_summaries(self, end_date: str) -> list[dict]:
        """
        Return daily_summaries rows for the 7 days ending on end_date (inclusive).
        end_date format: YYYY-MM-DD
        """
        assert self._conn is not None
        rows = self._conn.execute(
            """
            SELECT * FROM daily_summaries
            WHERE date <= ?
            ORDER BY date DESC
            LIMIT 7
            """,
            (end_date,),
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

    # ------------------------------------------------------------------
    # Sites sync
    # ------------------------------------------------------------------

    def sync_sites(self, domains: list[str], category: str = "custom") -> None:
        """
        Ensure every domain in the list exists in the sites table.
        Does not remove domains that were removed from config — they stay
        in the DB for historical reporting but are marked disabled.
        """
        assert self._conn is not None
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            with self._conn:
                for domain in domains:
                    self._conn.execute(
                        """
                        INSERT INTO sites (domain, category, date_added, enabled)
                        VALUES (?, ?, ?, 1)
                        ON CONFLICT(domain) DO UPDATE SET enabled = 1
                        """,
                        (domain, category, today),
                    )
        except sqlite3.Error as exc:
            logger.warning("Sites sync failed: %s", exc)

"""SQLite persistence for multi-window video performance snapshots."""

from __future__ import annotations

import os
import sqlite3
import threading
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping

from shared.core.performance_analyzer import normalize_performance_record


PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_PERFORMANCE_DB = os.path.join(PROJECT_ROOT, "data", "performance.sqlite3")
SCHEMA_VERSION = 2

RECORD_COLUMNS = (
    "snapshot_key", "video_id", "channel_id", "source_type", "source_url",
    "source_domain", "title", "story_type", "hook_type", "duration",
    "music_mood", "music_energy", "subtitle_style", "cta_mode",
    "visual_beat_count", "experiment_id", "experiment_variant",
    "experiment_variable", "experiment_value", "views", "average_watch_time",
    "watched_full_rate", "retention_2s", "retention_6s", "likes",
    "comments", "shares", "saves", "follows", "published_at",
    "measured_at", "measurement_window", "import_source",
)


class PerformanceStore:
    def __init__(self, db_path: str = DEFAULT_PERFORMANCE_DB):
        self.db_path = os.path.abspath(db_path)
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(
            self.db_path,
            timeout=30,
            check_same_thread=False,
        )
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA busy_timeout = 30000")
        self._connection.execute("PRAGMA journal_mode = WAL")
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        with self._lock, self._connection:
            self._connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS performance_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS performance_measurements (
                    snapshot_key TEXT PRIMARY KEY,
                    video_id TEXT NOT NULL,
                    channel_id TEXT NOT NULL,
                    source_type TEXT NOT NULL DEFAULT 'tiktok',
                    source_url TEXT NOT NULL DEFAULT '',
                    source_domain TEXT NOT NULL DEFAULT '',
                    title TEXT NOT NULL DEFAULT '',
                    story_type TEXT NOT NULL DEFAULT 'unknown',
                    hook_type TEXT NOT NULL DEFAULT 'unknown',
                    duration REAL NOT NULL DEFAULT 0 CHECK(duration >= 0),
                    music_mood TEXT NOT NULL DEFAULT 'unknown',
                    music_energy INTEGER NOT NULL DEFAULT 0 CHECK(music_energy >= 0),
                    subtitle_style TEXT NOT NULL DEFAULT 'unknown',
                    cta_mode TEXT NOT NULL DEFAULT 'unknown',
                    visual_beat_count INTEGER NOT NULL DEFAULT 0 CHECK(visual_beat_count >= 0),
                    experiment_id TEXT NOT NULL DEFAULT '',
                    experiment_variant TEXT NOT NULL DEFAULT '',
                    experiment_variable TEXT NOT NULL DEFAULT '',
                    experiment_value TEXT NOT NULL DEFAULT '',
                    views INTEGER NOT NULL DEFAULT 0 CHECK(views >= 0),
                    average_watch_time REAL NOT NULL DEFAULT 0 CHECK(average_watch_time >= 0),
                    watched_full_rate REAL NOT NULL DEFAULT 0 CHECK(watched_full_rate BETWEEN 0 AND 1),
                    retention_2s REAL NOT NULL DEFAULT 0 CHECK(retention_2s BETWEEN 0 AND 1),
                    retention_6s REAL NOT NULL DEFAULT 0 CHECK(retention_6s BETWEEN 0 AND 1),
                    likes INTEGER NOT NULL DEFAULT 0 CHECK(likes >= 0),
                    comments INTEGER NOT NULL DEFAULT 0 CHECK(comments >= 0),
                    shares INTEGER NOT NULL DEFAULT 0 CHECK(shares >= 0),
                    saves INTEGER NOT NULL DEFAULT 0 CHECK(saves >= 0),
                    follows INTEGER NOT NULL DEFAULT 0 CHECK(follows >= 0),
                    published_at TEXT NOT NULL DEFAULT '',
                    measured_at TEXT NOT NULL,
                    measurement_window TEXT NOT NULL,
                    import_source TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_performance_channel_measured
                    ON performance_measurements(channel_id, measured_at);
                CREATE INDEX IF NOT EXISTS idx_performance_video
                    ON performance_measurements(video_id, channel_id);
                CREATE INDEX IF NOT EXISTS idx_performance_window
                    ON performance_measurements(measurement_window);
                """
            )
            existing_columns = {
                row["name"] for row in self._connection.execute(
                    "PRAGMA table_info(performance_measurements)"
                ).fetchall()
            }
            migrations = {
                "music_energy": "INTEGER NOT NULL DEFAULT 0 CHECK(music_energy >= 0)",
                "subtitle_style": "TEXT NOT NULL DEFAULT 'unknown'",
                "cta_mode": "TEXT NOT NULL DEFAULT 'unknown'",
                "experiment_id": "TEXT NOT NULL DEFAULT ''",
                "experiment_variant": "TEXT NOT NULL DEFAULT ''",
                "experiment_variable": "TEXT NOT NULL DEFAULT ''",
                "experiment_value": "TEXT NOT NULL DEFAULT ''",
            }
            for column, definition in migrations.items():
                if column not in existing_columns:
                    self._connection.execute(
                        f"ALTER TABLE performance_measurements "
                        f"ADD COLUMN {column} {definition}"
                    )
            self._connection.execute(
                "CREATE INDEX IF NOT EXISTS idx_performance_experiment "
                "ON performance_measurements(experiment_id, experiment_variant)"
            )
            self._connection.execute(
                "INSERT INTO performance_meta(key, value) VALUES('schema_version', ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(SCHEMA_VERSION),),
            )

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def __enter__(self) -> "PerformanceStore":
        return self

    def __exit__(self, exc_type, exc, traceback) -> None:
        self.close()

    def _upsert_canonical(self, record: Mapping[str, Any]) -> None:
        now = datetime.now(timezone.utc).isoformat(timespec="seconds")
        columns = (*RECORD_COLUMNS, "created_at", "updated_at")
        values = [record.get(column, "") for column in RECORD_COLUMNS]
        values.extend((now, now))
        assignments = ", ".join(
            f"{column}=excluded.{column}"
            for column in RECORD_COLUMNS
            if column != "snapshot_key"
        )
        assignments += ", updated_at=excluded.updated_at"
        self._connection.execute(
            f"INSERT INTO performance_measurements ({', '.join(columns)}) "
            f"VALUES ({', '.join('?' for _ in columns)}) "
            f"ON CONFLICT(snapshot_key) DO UPDATE SET {assignments}",
            values,
        )

    def upsert(
        self,
        record: Mapping[str, Any],
        *,
        defaults: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        canonical = normalize_performance_record(record, defaults=defaults)
        with self._lock, self._connection:
            self._upsert_canonical(canonical)
        return canonical

    def upsert_many(
        self,
        records: Iterable[Mapping[str, Any]],
        *,
        defaults: Mapping[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        canonical = [
            normalize_performance_record(record, defaults=defaults)
            for record in records
        ]
        with self._lock, self._connection:
            for record in canonical:
                self._upsert_canonical(record)
        return canonical

    def list_measurements(
        self,
        *,
        channel_id: str = "",
        measurement_window: str = "",
        measured_from: str = "",
        measured_to: str = "",
        limit: int = 10_000,
    ) -> list[dict[str, Any]]:
        clauses = []
        params: list[Any] = []
        if channel_id:
            clauses.append("channel_id = ?")
            params.append(str(channel_id).lstrip("@"))
        if measurement_window:
            clauses.append("measurement_window = ?")
            params.append(str(measurement_window))
        if measured_from:
            clauses.append("measured_at >= ?")
            params.append(str(measured_from))
        if measured_to:
            clauses.append("measured_at <= ?")
            params.append(str(measured_to))
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        safe_limit = max(1, min(int(limit or 10_000), 100_000))
        query = (
            "SELECT * FROM performance_measurements"
            + where
            + " ORDER BY measured_at DESC, channel_id, video_id LIMIT ?"
        )
        params.append(safe_limit)
        with self._lock:
            rows = self._connection.execute(query, params).fetchall()
        return [dict(row) for row in rows]

    def count(self) -> int:
        with self._lock:
            row = self._connection.execute(
                "SELECT COUNT(*) AS total FROM performance_measurements"
            ).fetchone()
        return int(row["total"] if row else 0)

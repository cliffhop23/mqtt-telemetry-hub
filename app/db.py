"""SQLite persistence for device telemetry."""

from __future__ import annotations

import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

SCHEMA = """
CREATE TABLE IF NOT EXISTS devices (
    device_id TEXT PRIMARY KEY,
    first_seen TEXT NOT NULL,
    last_seen TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    device_id TEXT NOT NULL,
    metric TEXT NOT NULL,
    value REAL NOT NULL,
    ts TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_readings_device_metric_ts
    ON readings (device_id, metric, ts);
"""


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


class Database:
    """Thin, thread-safe SQLite wrapper (single connection + lock)."""

    def __init__(self, path: str | Path) -> None:
        self.path = str(path)
        self._conn: sqlite3.Connection | None = None
        self._lock = threading.Lock()

    def connect(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(self.path, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.executescript(SCHEMA)
        conn.commit()
        self._conn = conn

    def close(self) -> None:
        with self._lock:
            if self._conn is not None:
                self._conn.close()
                self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            raise RuntimeError("database is not connected")
        return self._conn

    def insert_reading(self, device_id: str, metric: str, value: float) -> dict[str, Any]:
        ts = utc_now()
        with self._lock:
            self.conn.execute(
                "INSERT INTO devices (device_id, first_seen, last_seen) VALUES (?, ?, ?) "
                "ON CONFLICT(device_id) DO UPDATE SET last_seen = excluded.last_seen",
                (device_id, ts, ts),
            )
            self.conn.execute(
                "INSERT INTO readings (device_id, metric, value, ts) VALUES (?, ?, ?, ?)",
                (device_id, metric, value, ts),
            )
            self.conn.commit()
        return {"device": device_id, "metric": metric, "value": value, "ts": ts}

    def devices(self) -> list[dict[str, Any]]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT device_id, first_seen, last_seen FROM devices ORDER BY device_id"
            ).fetchall()
        result = []
        for row in rows:
            latest = self.latest(row["device_id"])
            result.append(
                {
                    "device_id": row["device_id"],
                    "first_seen": row["first_seen"],
                    "last_seen": row["last_seen"],
                    "latest": latest,
                }
            )
        return result

    def latest(self, device_id: str) -> dict[str, float]:
        with self._lock:
            rows = self.conn.execute(
                "SELECT r.metric, r.value FROM readings r "
                "JOIN (SELECT metric, MAX(ts) AS ts FROM readings "
                "      WHERE device_id = ? GROUP BY metric) m "
                "ON r.metric = m.metric AND r.ts = m.ts WHERE r.device_id = ?",
                (device_id, device_id),
            ).fetchall()
        return {row["metric"]: row["value"] for row in rows}

    def readings(self, device_id: str, metric: str | None, limit: int) -> list[dict[str, Any]]:
        query = "SELECT metric, value, ts FROM readings WHERE device_id = ?"
        params: list[Any] = [device_id]
        if metric:
            query += " AND metric = ?"
            params.append(metric)
        query += " ORDER BY id DESC LIMIT ?"
        params.append(max(1, min(limit, 5000)))
        with self._lock:
            rows = self.conn.execute(query, params).fetchall()
        return [{"metric": r["metric"], "value": r["value"], "ts": r["ts"]} for r in reversed(rows)]

    def device_count(self) -> int:
        with self._lock:
            row = self.conn.execute("SELECT COUNT(*) AS n FROM devices").fetchone()
        return int(row["n"])

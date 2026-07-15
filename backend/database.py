"""
ชั้นจัดการฐานข้อมูล SQLite ของ Backend
เก็บผลการวัด/ประเมินแต่ละรอบที่ Raspberry Pi ส่งขึ้นมา
"""
from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.getenv("DB_PATH", os.path.join(BASE_DIR, "data", "readings.db"))

SCHEMA = """
CREATE TABLE IF NOT EXISTS readings (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp      TEXT    NOT NULL,
    station_id     TEXT,
    pm2_5          REAL    NOT NULL,   -- ค่าที่แสดง (AI ประเมิน)
    pm2_5_sensor   REAL,               -- ค่าจริงจาก PMS5003
    temperature    REAL,
    humidity       REAL,
    haze           TEXT,
    confidence     REAL,
    quality_label  TEXT,
    quality_level  TEXT,
    source         TEXT,               -- 'ai' หรือ 'sensor'
    image_filename TEXT
);
CREATE INDEX IF NOT EXISTS idx_readings_timestamp ON readings(timestamp);
"""


def init_db():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with get_conn() as conn:
        conn.executescript(SCHEMA)


@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def insert_reading(data: dict) -> int:
    cols = ["timestamp", "station_id", "pm2_5", "pm2_5_sensor", "temperature",
            "humidity", "haze", "confidence", "quality_label", "quality_level",
            "source", "image_filename"]
    values = [data.get(c) for c in cols]
    placeholders = ",".join("?" for _ in cols)
    with get_conn() as conn:
        cur = conn.execute(
            f"INSERT INTO readings ({','.join(cols)}) VALUES ({placeholders})",
            values,
        )
        return cur.lastrowid


def get_latest() -> dict | None:
    with get_conn() as conn:
        row = conn.execute(
            "SELECT * FROM readings ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None


def get_history(limit: int = 10) -> list[dict]:
    with get_conn() as conn:
        rows = conn.execute(
            "SELECT * FROM readings ORDER BY id DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_trend(range_key: str = "today") -> list[dict]:
    """
    ดึงข้อมูลกราฟแนวโน้มตามช่วงเวลา
    range_key: 'today' | '7d' | '30d'
    """
    now = datetime.now()
    if range_key == "7d":
        since = now - timedelta(days=7)
    elif range_key == "30d":
        since = now - timedelta(days=30)
    else:  # today
        since = now.replace(hour=0, minute=0, second=0, microsecond=0)

    with get_conn() as conn:
        rows = conn.execute(
            "SELECT timestamp, pm2_5, temperature, humidity FROM readings "
            "WHERE timestamp >= ? ORDER BY timestamp ASC",
            (since.isoformat(timespec="seconds"),),
        ).fetchall()
        return [dict(r) for r in rows]


def get_daily_average(days: int = 1) -> float | None:
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    with get_conn() as conn:
        row = conn.execute(
            "SELECT AVG(pm2_5) AS avg FROM readings WHERE timestamp >= ?", (since,)
        ).fetchone()
        return round(row["avg"], 1) if row and row["avg"] is not None else None


def iter_all_rows():
    """สำหรับ export ทั้งหมด"""
    with get_conn() as conn:
        for row in conn.execute("SELECT * FROM readings ORDER BY id ASC"):
            yield dict(row)

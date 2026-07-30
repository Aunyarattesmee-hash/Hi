# -*- coding: utf-8 -*-
"""
database.py — เก็บข้อมูลลงไฟล์ฐานข้อมูล SQLite (เบา ไม่ต้องติดตั้งเซิร์ฟเวอร์)
"""

import sqlite3
import time


class Database:
    def __init__(self, db_file="pm25.db"):
        # check_same_thread=False เพื่อให้เรียกจากหลาย thread ได้ (เว็บ + ตัวอ่านเซนเซอร์)
        self.conn = sqlite3.connect(db_file, check_same_thread=False)
        self.conn.row_factory = sqlite3.Row
        self._create_table()

    def _create_table(self):
        self.conn.execute(
            """
            CREATE TABLE IF NOT EXISTS readings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                ts          REAL,     -- เวลา (epoch seconds)
                pm2_5       REAL,     -- ค่าฝุ่น PM2.5 (µg/m³)
                pm10        REAL,
                temperature REAL,     -- °C
                humidity    REAL,     -- %
                image       TEXT      -- ชื่อไฟล์ภาพ (ถ้ามี)
            )
            """
        )
        self.conn.commit()

    def insert(self, pm2_5, pm10, temperature, humidity, image=None):
        self.conn.execute(
            "INSERT INTO readings (ts, pm2_5, pm10, temperature, humidity, image)"
            " VALUES (?, ?, ?, ?, ?, ?)",
            (time.time(), pm2_5, pm10, temperature, humidity, image),
        )
        self.conn.commit()

    def latest(self):
        """ค่าล่าสุด 1 แถว (หรือ None ถ้ายังไม่มีข้อมูล)"""
        row = self.conn.execute(
            "SELECT * FROM readings ORDER BY ts DESC LIMIT 1"
        ).fetchone()
        return dict(row) if row else None

    def history(self, limit=200):
        """ข้อมูลย้อนหลัง (เรียงเก่า -> ใหม่) เอาไว้วาดกราฟ"""
        rows = self.conn.execute(
            "SELECT * FROM readings ORDER BY ts DESC LIMIT ?", (limit,)
        ).fetchall()
        return [dict(r) for r in reversed(rows)]

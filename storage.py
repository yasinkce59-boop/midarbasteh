# -*- coding: utf-8 -*-
"""
لایه‌ی ذخیره‌سازی: ثبت پلاک‌های شناسایی‌شده در دیتابیس SQLite و فایل CSV،
به همراه جلوگیری از ثبت تکراری یک پلاک در بازه‌ی زمانی کوتاه.
"""

import csv
import os
import sqlite3
import threading
import time
from datetime import datetime

import config


class PlateLogger:
    def __init__(self):
        self._db_lock = threading.Lock()
        self._init_db()
        self._last_seen = {}  # (camera_name, plate_text) -> last_logged_timestamp

    def _init_db(self):
        self.conn = sqlite3.connect(config.DB_PATH, check_same_thread=False)
        cur = self.conn.cursor()
        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS plates (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_name TEXT,
                plate_text TEXT NOT NULL,
                confidence REAL,
                timestamp TEXT NOT NULL,
                plate_image_path TEXT,
                vehicle_image_path TEXT
            )
            """
        )
        self.conn.commit()

        # سازگاری با پایگاه‌داده‌های قدیمی‌تر که ستون camera_name را نداشتند
        cur.execute("PRAGMA table_info(plates)")
        existing_cols = {row[1] for row in cur.fetchall()}
        if "camera_name" not in existing_cols:
            cur.execute("ALTER TABLE plates ADD COLUMN camera_name TEXT")
            self.conn.commit()

        cur.execute(
            """
            CREATE TABLE IF NOT EXISTS crossing_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_name TEXT,
                zone_name TEXT,
                object_category TEXT NOT NULL,
                confidence REAL,
                timestamp TEXT NOT NULL,
                image_path TEXT
            )
            """
        )
        self.conn.commit()

        if not os.path.exists(config.CSV_PATH):
            with open(config.CSV_PATH, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(
                    ["camera_name", "plate_text", "confidence", "timestamp",
                     "plate_image_path", "vehicle_image_path"]
                )

    def should_log(self, plate_text: str, camera_name: str = "") -> bool:
        """بررسی می‌کند آیا این پلاک (در این دوربین) اخیراً ثبت شده یا نه."""
        now = time.time()
        key = (camera_name, plate_text)
        last = self._last_seen.get(key)
        if last is not None and (now - last) < config.DUPLICATE_COOLDOWN_SECONDS:
            return False
        return True

    def log_plate(self, plate_text: str, confidence: float, plate_image_path: str = "",
                  vehicle_image_path: str = "", camera_name: str = ""):
        now = time.time()
        self._last_seen[(camera_name, plate_text)] = now
        timestamp = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")

        with self._db_lock:
            cur = self.conn.cursor()
            cur.execute(
                """INSERT INTO plates
                   (camera_name, plate_text, confidence, timestamp, plate_image_path, vehicle_image_path)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (camera_name, plate_text, confidence, timestamp, plate_image_path, vehicle_image_path),
            )
            self.conn.commit()

            with open(config.CSV_PATH, "a", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(
                    [camera_name, plate_text, f"{confidence:.2f}", timestamp,
                     plate_image_path, vehicle_image_path]
                )

        print(f"[ثبت شد] دوربین: {camera_name} | پلاک: {plate_text} | اطمینان: {confidence:.2f} | زمان: {timestamp}")

    def fetch_records(self, date_filter=None, plate_filter=None, camera_filter=None, limit=200):
        """برای رابط گرافیکی/گزارش: بازیابی رکوردها با فیلتر اختیاری."""
        query = """SELECT id, camera_name, plate_text, confidence, timestamp,
                          plate_image_path, vehicle_image_path
                   FROM plates WHERE 1=1"""
        params = []
        if date_filter:
            query += " AND timestamp LIKE ?"
            params.append(f"{date_filter}%")
        if plate_filter:
            query += " AND plate_text LIKE ?"
            params.append(f"%{plate_filter}%")
        if camera_filter:
            query += " AND camera_name LIKE ?"
            params.append(f"%{camera_filter}%")
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._db_lock:
            cur = self.conn.cursor()
            cur.execute(query, params)
            return cur.fetchall()

    def close(self):
        self.conn.close()

    # ------------------------------------------------------------------
    # رویدادهای عبور از خط/محدوده (فرد، حیوان، خودرو و غیره)
    # ------------------------------------------------------------------
    def should_log_crossing(self, camera_name: str, zone_name: str, category: str) -> bool:
        """جلوگیری از ثبت تکراری همان دسته‌ی شیء در همان ناحیه طی چند ثانیه‌ی اخیر."""
        now = time.time()
        key = ("crossing", camera_name, zone_name, category)
        last = self._last_seen.get(key)
        if last is not None and (now - last) < config.CROSSING_COOLDOWN_SECONDS:
            return False
        return True

    def log_crossing_event(self, camera_name: str, zone_name: str, category: str,
                            confidence: float, image_path: str = ""):
        now = time.time()
        self._last_seen[("crossing", camera_name, zone_name, category)] = now
        timestamp = datetime.fromtimestamp(now).strftime("%Y-%m-%d %H:%M:%S")

        with self._db_lock:
            cur = self.conn.cursor()
            cur.execute(
                """INSERT INTO crossing_events
                   (camera_name, zone_name, object_category, confidence, timestamp, image_path)
                   VALUES (?, ?, ?, ?, ?, ?)""",
                (camera_name, zone_name, category, confidence, timestamp, image_path),
            )
            self.conn.commit()

        print(f"[هشدار عبور] دوربین: {camera_name} | ناحیه: {zone_name} | "
              f"نوع: {category} | اطمینان: {confidence:.2f} | زمان: {timestamp}")

    def fetch_crossing_events(self, date_filter=None, camera_filter=None,
                               category_filter=None, limit=200):
        query = """SELECT id, camera_name, zone_name, object_category, confidence,
                          timestamp, image_path
                   FROM crossing_events WHERE 1=1"""
        params = []
        if date_filter:
            query += " AND timestamp LIKE ?"
            params.append(f"{date_filter}%")
        if camera_filter:
            query += " AND camera_name LIKE ?"
            params.append(f"%{camera_filter}%")
        if category_filter:
            query += " AND object_category LIKE ?"
            params.append(f"%{category_filter}%")
        query += " ORDER BY id DESC LIMIT ?"
        params.append(limit)

        with self._db_lock:
            cur = self.conn.cursor()
            cur.execute(query, params)
            return cur.fetchall()

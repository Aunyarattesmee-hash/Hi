"""
จัดการ Dataset ที่เก็บลง Micro SD Card
แต่ละแถว = 1 การเก็บข้อมูล: ภาพท้องฟ้า + ค่าจริงจากเซนเซอร์ (Ground Truth)

รูปแบบไฟล์: CSV (dataset.csv) — เปิดดู/แก้ไข/ย้ายไป train ที่อื่นได้ง่าย
"""
from __future__ import annotations

import csv
import os
from datetime import datetime

import numpy as np

import config
from model import extract_features_from_path, FEATURE_NAMES

CSV_HEADER = (
    ["timestamp", "image_path", "pm2_5", "pm1_0", "pm10",
     "temperature", "humidity"]
    + FEATURE_NAMES
)


def append_sample(image_path: str, pm2_5: float, pm1_0: float, pm10: float,
                  temperature: float, humidity: float,
                  features: np.ndarray | None = None):
    """เพิ่ม 1 แถวลง dataset.csv (สกัดฟีเจอร์จากภาพให้อัตโนมัติถ้าไม่ส่งมา)"""
    config.ensure_dirs()
    if features is None:
        features = extract_features_from_path(image_path)

    new_file = not os.path.exists(config.DATASET_CSV)
    with open(config.DATASET_CSV, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if new_file:
            writer.writerow(CSV_HEADER)
        row = [
            datetime.now().isoformat(timespec="seconds"),
            image_path, pm2_5, pm1_0, pm10, temperature, humidity,
        ] + [float(v) for v in features]
        writer.writerow(row)


def load_training_data():
    """
    อ่าน dataset.csv คืน (X, y) สำหรับการเทรน
    X = ฟีเจอร์ภาพ, y = ค่า PM2.5 จริง
    """
    if not os.path.exists(config.DATASET_CSV):
        raise FileNotFoundError(
            f"ยังไม่มี dataset ({config.DATASET_CSV}) — เก็บข้อมูลก่อนด้วย collector.py"
        )
    X, y = [], []
    with open(config.DATASET_CSV, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            try:
                feats = [float(row[name]) for name in FEATURE_NAMES]
                X.append(feats)
                y.append(float(row["pm2_5"]))
            except (KeyError, ValueError):
                continue
    return np.array(X, dtype=np.float32), np.array(y, dtype=np.float32)


def count_samples() -> int:
    if not os.path.exists(config.DATASET_CSV):
        return 0
    with open(config.DATASET_CSV, encoding="utf-8") as f:
        return max(0, sum(1 for _ in f) - 1)  # ลบ header

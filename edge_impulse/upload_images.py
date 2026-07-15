"""
อัปโหลดภาพ + ค่า PM2.5 ขึ้น Edge Impulse โดยตรงผ่าน Ingestion API

ต่างจาก export_dataset.py ตรงที่ส่งขึ้นคลาวด์ให้เลย ไม่ต้องลากวางเอง
โดยแนบ label = ค่า PM2.5 จริง (สำหรับ Regression) และ metadata (อุณหภูมิ/ความชื้น)

ต้องมี:
  - EI_API_KEY : API Key ของโปรเจกต์ (Studio -> Dashboard -> Keys)
                 ตั้งผ่าน environment variable หรือใส่ด้วย --api-key

วิธีใช้:
    export EI_API_KEY="ei_xxxxxxxx"
    python upload_images.py                 # อัปโหลดทั้งหมด (แบ่ง train/test อัตโนมัติ)
    python upload_images.py --test-ratio 0  # อัปโหลดเป็น training ทั้งหมด
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import sys

import requests

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "device"))
import config  # noqa: E402

INGESTION_URL = "https://ingestion.edgeimpulse.com/api/{split}/files"


def upload_one(api_key: str, split: str, image_path: str, label: str, metadata: dict):
    url = INGESTION_URL.format(split=split)
    headers = {
        "x-api-key": api_key,
        "x-label": label,                     # ค่า PM2.5 (regression target)
        "x-metadata": json.dumps(metadata),   # ข้อมูลเสริม
        "x-add-date-id": "1",
    }
    with open(image_path, "rb") as f:
        files = {"data": (os.path.basename(image_path), f, "image/jpeg")}
        resp = requests.post(url, headers=headers, files=files, timeout=30)
    return resp


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--api-key", default=os.getenv("EI_API_KEY", ""))
    ap.add_argument("--test-ratio", type=float, default=0.2)
    args = ap.parse_args()

    if not args.api_key:
        print("❌ ไม่พบ EI_API_KEY — ตั้งค่าด้วย: export EI_API_KEY=\"ei_xxx\"")
        print("   (หาได้จาก Edge Impulse Studio -> Dashboard -> Keys)")
        sys.exit(1)

    if not os.path.exists(config.DATASET_CSV):
        print(f"❌ ไม่พบ dataset: {config.DATASET_CSV}")
        sys.exit(1)

    with open(config.DATASET_CSV, newline="", encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    ok = fail = skip = 0
    step = round(1 / max(args.test_ratio, 1e-6)) if args.test_ratio > 0 else 0
    for i, r in enumerate(rows):
        src = r["image_path"]
        if not os.path.exists(src):
            skip += 1
            continue
        label = f"{float(r['pm2_5']):.2f}"
        split = "testing" if (step and i % step == 0) else "training"
        meta = {
            "temperature": r.get("temperature", ""),
            "humidity": r.get("humidity", ""),
            "pm2_5_sensor": r.get("pm2_5", ""),
            "station_id": config.STATION_ID,
        }
        try:
            resp = upload_one(args.api_key, split, src, label, meta)
            if resp.status_code == 200:
                ok += 1
                print(f"  ✓ [{split:8}] {os.path.basename(src)}  (PM2.5={label})")
            else:
                fail += 1
                print(f"  ✗ {os.path.basename(src)} -> HTTP {resp.status_code}: {resp.text[:120]}")
        except Exception as err:
            fail += 1
            print(f"  ✗ {os.path.basename(src)} -> {err}")

    print("-" * 50)
    print(f"อัปโหลดสำเร็จ {ok} | ล้มเหลว {fail} | ข้าม {skip}")
    if ok:
        print("เปิด Edge Impulse Studio -> Data acquisition เพื่อตรวจสอบข้อมูล")


if __name__ == "__main__":
    main()

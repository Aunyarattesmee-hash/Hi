"""
เตรียมชุดข้อมูล (Dataset) สำหรับอัปโหลดขึ้น Edge Impulse — แบบออฟไลน์

อ่าน device/data/dataset.csv + ภาพ แล้วสร้างโฟลเดอร์ export/ ที่:
  - ตั้งชื่อไฟล์ภาพให้ฝัง "ค่า PM2.5" ไว้ในชื่อ (รูปแบบที่ Edge Impulse อ่าน label ได้)
        <label>.<ชื่อเดิม>.jpg      เช่น  34.50.sky_20260715.jpg
  - แบ่ง train/ และ test/ อัตโนมัติ (ค่าเริ่มต้น 80/20)
  - สร้าง labels.csv สรุปทุกไฟล์ (image, pm2_5, temperature, humidity)

จากนั้นนำโฟลเดอร์ export/train และ export/test ไป "ลากวางอัปโหลด" ใน
Edge Impulse Studio (Data acquisition) หรือใช้ edge-impulse-uploader ก็ได้

วิธีใช้:
    python export_dataset.py
    python export_dataset.py --test-ratio 0.2
"""
from __future__ import annotations

import argparse
import csv
import os
import shutil
import sys

# ให้ import config/dataset ของฝั่ง device ได้
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "device"))
import config  # noqa: E402

EXPORT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "export")


def safe_label(pm25: float) -> str:
    """Edge Impulse ใช้ค่าตัวเลขเป็น label ได้ (regression) — จำกัดทศนิยม 2 ตำแหน่ง"""
    return f"{float(pm25):.2f}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--test-ratio", type=float, default=0.2,
                    help="สัดส่วนข้อมูลทดสอบ (0-1)")
    args = ap.parse_args()

    if not os.path.exists(config.DATASET_CSV):
        print(f"❌ ไม่พบ dataset: {config.DATASET_CSV} — เก็บข้อมูลก่อนด้วย collector.py")
        sys.exit(1)

    # ล้างของเดิม
    if os.path.exists(EXPORT_DIR):
        shutil.rmtree(EXPORT_DIR)
    train_dir = os.path.join(EXPORT_DIR, "train")
    test_dir = os.path.join(EXPORT_DIR, "test")
    os.makedirs(train_dir, exist_ok=True)
    os.makedirs(test_dir, exist_ok=True)

    rows = []
    with open(config.DATASET_CSV, newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            rows.append(r)

    manifest = []
    n_train = n_test = n_skip = 0
    for i, r in enumerate(rows):
        src = r["image_path"]
        if not os.path.exists(src):
            n_skip += 1
            continue
        pm25 = float(r["pm2_5"])
        label = safe_label(pm25)
        base = os.path.basename(src)
        # ทุกไฟล์ที่ 5 ไปเป็นชุดทดสอบ (แบ่งแบบ deterministic)
        is_test = (i % round(1 / max(args.test_ratio, 1e-6)) == 0) if args.test_ratio > 0 else False
        dst_dir = test_dir if is_test else train_dir
        new_name = f"{label}.{base}"
        shutil.copy2(src, os.path.join(dst_dir, new_name))
        manifest.append({
            "split": "test" if is_test else "train",
            "image": new_name,
            "pm2_5": label,
            "temperature": r.get("temperature", ""),
            "humidity": r.get("humidity", ""),
        })
        if is_test:
            n_test += 1
        else:
            n_train += 1

    # labels.csv
    with open(os.path.join(EXPORT_DIR, "labels.csv"), "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=["split", "image", "pm2_5", "temperature", "humidity"])
        w.writeheader()
        w.writerows(manifest)

    print("=" * 56)
    print("  เตรียมชุดข้อมูลสำหรับ Edge Impulse เสร็จแล้ว")
    print("=" * 56)
    print(f"  train : {n_train} ภาพ  ->  {train_dir}")
    print(f"  test  : {n_test} ภาพ  ->  {test_dir}")
    if n_skip:
        print(f"  ข้าม  : {n_skip} แถว (ไม่พบไฟล์ภาพ)")
    print(f"  สรุป  : {os.path.join(EXPORT_DIR, 'labels.csv')}")
    print("\nขั้นตอนถัดไป: อัปโหลดโฟลเดอร์ train/ และ test/ เข้า Edge Impulse")
    print("  วิธี A (ลากวาง): Studio -> Data acquisition -> Upload data")
    print("  วิธี B (CLI):   ดูใน edge_impulse/README.md")


if __name__ == "__main__":
    main()

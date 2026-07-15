"""
สคริปต์เทรนโมเดล AI (ขั้นตอน "AI Model Training" + "Model Evaluation" ในรูปที่ 1)

การทำงาน:
  1. โหลด Dataset (ภาพ + PM2.5 + Temp + RH) จาก SD card
  2. เทรน regressor เรียนรู้ความสัมพันธ์ ภาพท้องฟ้า -> ค่า PM2.5
  3. ประเมินผล (MAE)
  4. ผ่านเกณฑ์ (MAE <= threshold) ? -> Deploy Model (บันทึกไฟล์โมเดล)
                                    -> ไม่ผ่าน: แจ้งให้ "เพิ่มข้อมูล Train ใหม่"

รันด้วย:  python train.py
"""
from __future__ import annotations

import sys

import config
import dataset
from model import PM25Model


def main():
    print("=" * 60)
    print("  AI Model Training — ประเมินค่า PM2.5 จากภาพท้องฟ้า")
    print("=" * 60)

    n = dataset.count_samples()
    print(f"จำนวนตัวอย่างใน dataset: {n}")
    if n < 10:
        print("❌ ข้อมูลน้อยเกินไป — โปรดเก็บข้อมูลเพิ่มด้วย collector.py ก่อน")
        sys.exit(1)

    X, y = dataset.load_training_data()
    print(f"โหลดข้อมูลสำเร็จ: X={X.shape}, y={y.shape}")

    model = PM25Model()
    print("กำลังเทรนโมเดล...")
    result = model.train(X, y)
    mae = result["mae"]
    print(f"ผลการประเมิน (Model Evaluation): MAE = {mae:.2f} µg/m³ "
          f"(train={result['n_train']}, test={result['n_test']})")

    # ผ่านเกณฑ์ ?
    if mae <= config.MODEL_MAE_THRESHOLD:
        model.save(config.MODEL_PATH)
        print(f"✅ ผ่านเกณฑ์ (<= {config.MODEL_MAE_THRESHOLD}) — Deploy Model แล้ว")
        print(f"   บันทึกโมเดลที่: {config.MODEL_PATH}")
    else:
        print(f"⚠️  ไม่ผ่านเกณฑ์ (MAE {mae:.2f} > {config.MODEL_MAE_THRESHOLD})")
        print("   โปรดเพิ่มข้อมูลและ Train ใหม่ (เก็บภาพในสภาพอากาศหลากหลายขึ้น)")
        sys.exit(2)


if __name__ == "__main__":
    main()

"""
โปรแกรมหลักที่รันบน Raspberry Pi 5 (ขั้นตอนตามรูปที่ 1)

ลูปการทำงานแต่ละรอบ:
  1. Webcam (C270) ถ่ายภาพท้องฟ้า
  2. PMS5003 + DHT22 วัด PM2.5 / อุณหภูมิ / ความชื้น จริง (Ground Truth)
  3. Raspberry Pi 5 เก็บภาพ + ข้อมูลเซนเซอร์ ลง Dataset (Micro SD Card)
  4. ถ้ามีโมเดลแล้ว -> AI วิเคราะห์ภาพใหม่ ประเมิน PM2.5 + เปรียบเทียบกับค่าจริง
  5. ส่งผลขึ้น Backend (Dashboard)

โหมดการทำงาน:
  python collector.py            # รันด้วยเซนเซอร์จริง วนลูปตลอด
  python collector.py --once     # รันรอบเดียว
  python collector.py --simulate # โหมดจำลอง (ไม่มีฮาร์ดแวร์ ใช้ทดสอบระบบ/เว็บ)
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

import config
import dataset
from model import PM25Model, extract_features, air_quality_category, haze_level


# ---------------------------------------------------------------------------
# การอ่านค่าจริงจากฮาร์ดแวร์
# ---------------------------------------------------------------------------
def read_hardware():
    """ถ่ายภาพ + อ่านเซนเซอร์จริง คืน dict ข้อมูลดิบ"""
    from camera import SkyCamera
    from sensors.pms5003 import PMS5003
    from sensors.dht22 import DHT22

    cam = SkyCamera(config.CAMERA_INDEX, config.CAMERA_WIDTH, config.CAMERA_HEIGHT)
    frame, image_path = cam.capture()

    with PMS5003(config.PMS5003_PORT, config.PMS5003_BAUD) as pms:
        pm = pms.read()

    dht = DHT22(config.DHT22_PIN, config.DHT_TYPE)
    try:
        th = dht.read()
    finally:
        dht.close()

    return {
        "frame": frame,
        "image_path": image_path,
        "pm2_5": pm.pm2_5,
        "pm1_0": pm.pm1_0,
        "pm10": pm.pm10,
        "temperature": th.temperature,
        "humidity": th.humidity,
    }


def read_simulated():
    """สร้างข้อมูลจำลอง (ภาพ + ค่าเซนเซอร์) สำหรับทดสอบโดยไม่มีฮาร์ดแวร์"""
    import numpy as np
    try:
        import cv2
    except ImportError:
        cv2 = None

    config.ensure_dirs()
    # สุ่มค่า PM2.5 จริงในช่วงสมจริง
    pm2_5 = float(np.clip(np.random.normal(35, 15), 3, 160))

    # สร้างภาพท้องฟ้าจำลอง: ค่าฝุ่นสูง -> ฟ้าขาว/เทา (haze), ค่าต่ำ -> ฟ้าน้ำเงินสด
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    image_path = os.path.join(config.IMAGE_DIR, f"sky_{ts}.jpg")
    haze = np.clip(pm2_5 / 160.0, 0, 1)
    if cv2 is not None:
        h, w = 480, 640
        top = np.array([230, 180, 90], dtype=np.float32)      # ฟ้าสดใส (BGR)
        gray = np.array([200, 200, 200], dtype=np.float32)    # ฟ้าขุ่น
        sky = top * (1 - haze) + gray * haze
        img = np.tile(sky, (h, w, 1)).astype(np.float32)
        grad = np.linspace(1.05, 0.9, h).reshape(h, 1, 1)     # ไล่เฉดบน-ล่าง
        img = np.clip(img * grad + np.random.normal(0, 4, (h, w, 3)), 0, 255)
        img = img.astype(np.uint8)
        cv2.imwrite(image_path, img)
        frame = img
    else:
        frame = None

    return {
        "frame": frame,
        "image_path": image_path,
        "pm2_5": pm2_5,
        "pm1_0": pm2_5 * 0.7,
        "pm10": pm2_5 * 1.4,
        "temperature": float(np.clip(np.random.normal(29, 2), 20, 40)),
        "humidity": float(np.clip(np.random.normal(73, 8), 30, 99)),
    }


# ---------------------------------------------------------------------------
# ส่งข้อมูลขึ้น Backend
# ---------------------------------------------------------------------------
def push_to_backend(payload: dict, image_path: str):
    try:
        import requests
    except ImportError:
        print("  (ข้าม upload: ไม่พบไลบรารี requests)")
        return
    try:
        with open(image_path, "rb") as img:
            files = {"image": (os.path.basename(image_path), img, "image/jpeg")}
            data = {k: str(v) for k, v in payload.items()}
            headers = {"X-API-Key": config.BACKEND_API_KEY}
            resp = requests.post(config.BACKEND_INGEST_ENDPOINT,
                                 data=data, files=files, headers=headers, timeout=15)
        if resp.status_code in (200, 201):
            print("  ↑ ส่งข้อมูลขึ้น Dashboard สำเร็จ")
        else:
            print(f"  ⚠️  ส่งข้อมูลไม่สำเร็จ: HTTP {resp.status_code} {resp.text[:120]}")
    except Exception as err:
        print(f"  ⚠️  เชื่อมต่อ backend ไม่ได้: {err}")


# ---------------------------------------------------------------------------
# หนึ่งรอบการทำงาน
# ---------------------------------------------------------------------------
def run_once(simulate: bool = False, model: PM25Model | None = None):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] เริ่มเก็บข้อมูล 1 รอบ")

    raw = read_simulated() if simulate else read_hardware()
    print(f"  📷 ภาพ: {os.path.basename(raw['image_path'])}")
    print(f"  🌫️  PM2.5 จริง = {raw['pm2_5']:.1f} µg/m³ | "
          f"🌡️ {raw['temperature']:.1f}°C | 💧 {raw['humidity']:.0f}%")

    # 3) เก็บลง Dataset (Ground Truth)
    features = None
    if raw["frame"] is not None:
        features = extract_features(raw["frame"])
    dataset.append_sample(
        image_path=raw["image_path"],
        pm2_5=raw["pm2_5"], pm1_0=raw["pm1_0"], pm10=raw["pm10"],
        temperature=raw["temperature"], humidity=raw["humidity"],
        features=features,
    )

    # 4) ถ้ามีโมเดล -> AI วิเคราะห์ภาพ + เปรียบเทียบกับค่าจริง
    predicted = None
    if model is not None and features is not None:
        pred = model.predict(features)
        predicted = pred.as_dict()
        err = abs(pred.pm25 - raw["pm2_5"])
        print(f"  🤖 AI ประเมิน = {pred.pm25:.1f} µg/m³ "
              f"({pred.haze}, เชื่อมั่น {pred.confidence:.0f}%) | "
              f"ต่างจากค่าจริง {err:.1f}")

    # ค่าที่จะแสดงบน Dashboard: ใช้ค่าที่ AI ประเมิน ถ้ายังไม่มีโมเดลใช้ค่าเซนเซอร์
    display_pm25 = predicted["pm25"] if predicted else round(raw["pm2_5"], 1)
    cat = air_quality_category(display_pm25)
    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "station_id": config.STATION_ID,
        "pm2_5": display_pm25,
        "pm2_5_sensor": round(raw["pm2_5"], 1),   # ค่าจริงจาก PMS5003
        "temperature": round(raw["temperature"], 1),
        "humidity": round(raw["humidity"], 0),
        "haze": haze_level(display_pm25),
        "confidence": predicted["confidence"] if predicted else 100.0,
        "quality_label": cat["label"],
        "quality_level": cat["level"],
        "source": "ai" if predicted else "sensor",
    }

    # 5) ส่งขึ้น Dashboard
    if config.PUSH_TO_BACKEND:
        push_to_backend(payload, raw["image_path"])

    return payload


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------
def main():
    parser = argparse.ArgumentParser(description="ตัวเก็บข้อมูล PM2.5 บน Raspberry Pi 5")
    parser.add_argument("--once", action="store_true", help="รันรอบเดียวแล้วจบ")
    parser.add_argument("--simulate", action="store_true", help="โหมดจำลอง (ไม่มีฮาร์ดแวร์)")
    parser.add_argument("--interval", type=int, default=config.SAMPLE_INTERVAL_SEC,
                        help="ระยะเวลาระหว่างรอบ (วินาที)")
    args = parser.parse_args()

    config.ensure_dirs()

    # โหลดโมเดลถ้ามี (Deploy Model แล้ว)
    model = None
    if PM25Model.exists(config.MODEL_PATH):
        model = PM25Model.load(config.MODEL_PATH)
        print(f"โหลดโมเดล AI จาก {config.MODEL_PATH}")
    else:
        print("ยังไม่มีโมเดล AI — จะเก็บ Dataset และแสดงค่าจากเซนเซอร์ไปก่อน")
        print("เมื่อเก็บข้อมูลพอแล้วให้รัน:  python train.py")

    if args.once:
        run_once(simulate=args.simulate, model=model)
        return

    print(f"เริ่มทำงานแบบวนลูป (ทุก {args.interval} วินาที) — กด Ctrl+C เพื่อหยุด")
    try:
        while True:
            try:
                run_once(simulate=args.simulate, model=model)
            except Exception as err:
                print(f"  ❌ เกิดข้อผิดพลาดในรอบนี้: {err}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nหยุดการทำงานแล้ว")


if __name__ == "__main__":
    main()

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
# เลือกโมเดล AI ที่จะใช้ (Edge Impulse .eim มาก่อน, ไม่มีก็ใช้ scikit-learn .joblib)
# ---------------------------------------------------------------------------
def load_model():
    """
    คืน (model, kind):
      kind = "edge_impulse" -> โมเดล .eim ที่เทรนจาก Edge Impulse (ทำนายจากภาพ)
      kind = "sklearn"      -> โมเดล .joblib ที่เทรนด้วย train.py (ทำนายจากฟีเจอร์)
      kind = None           -> ยังไม่มีโมเดล ใช้ค่าจากเซนเซอร์ไปก่อน
    """
    # 1) Edge Impulse — ถ้ามีไฟล์ .eim ให้ใช้ก่อน
    if os.path.exists(config.EIM_MODEL_PATH):
        # ei_inference.py อยู่ในโฟลเดอร์ edge_impulse/ (นอก device/) ต้องเพิ่ม path
        ei_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "edge_impulse")
        if ei_dir not in sys.path:
            sys.path.insert(0, ei_dir)
        try:
            from ei_inference import EdgeImpulsePM25
            model = EdgeImpulsePM25(config.EIM_MODEL_PATH)
            print(f"โหลดโมเดล Edge Impulse จาก {config.EIM_MODEL_PATH}")
            return model, "edge_impulse"
        except Exception as err:
            print(f"⚠️  พบไฟล์ .eim แต่โหลดไม่สำเร็จ ({err}) — จะลองใช้โมเดล scikit-learn แทน")

    # 2) scikit-learn — โมเดลที่เทรนด้วย train.py
    if PM25Model.exists(config.MODEL_PATH):
        print(f"โหลดโมเดล AI (scikit-learn) จาก {config.MODEL_PATH}")
        return PM25Model.load(config.MODEL_PATH), "sklearn"

    # 3) ยังไม่มีโมเดล
    return None, None


# ---------------------------------------------------------------------------
# การอ่านค่าจริงจากฮาร์ดแวร์
# ---------------------------------------------------------------------------
def read_hardware():
    """
    ถ่ายภาพ (จำเป็น) + อ่านเซนเซอร์ฝุ่น/อุณหภูมิ (ไม่บังคับ) คืน dict ข้อมูลดิบ

    กล้อง = จำเป็น เพราะโมเดล AI ต้องใช้ภาพ
    เซนเซอร์ฝุ่น PMS5003 / อุณหภูมิ DHT = ถ้าอ่านไม่ได้จะข้าม (คืน None)
    เพื่อให้ยังถ่ายภาพ + รันโมเดล AI + ส่งขึ้น Dashboard ได้ แม้เซนเซอร์ยังไม่พร้อม
    """
    from camera import SkyCamera

    # --- กล้อง (จำเป็น) ---
    cam = SkyCamera(config.CAMERA_INDEX, config.CAMERA_WIDTH, config.CAMERA_HEIGHT)
    frame, image_path = cam.capture()

    # --- เซนเซอร์ฝุ่น PMS5003 (ไม่บังคับ) ---
    pm2_5 = pm1_0 = pm10 = None
    try:
        from sensors.pms5003 import PMS5003
        with PMS5003(config.PMS5003_PORT, config.PMS5003_BAUD) as pms:
            pm = pms.read()
        pm2_5, pm1_0, pm10 = pm.pm2_5, pm.pm1_0, pm.pm10
    except Exception as err:
        print(f"  ⚠️  อ่านเซนเซอร์ฝุ่น (PMS5003) ไม่ได้ — ข้ามไปก่อน: {err}")

    # --- เซนเซอร์อุณหภูมิ/ความชื้น DHT (ไม่บังคับ) ---
    temperature = humidity = None
    try:
        from sensors.dht22 import DHT22
        dht = DHT22(config.DHT22_PIN, config.DHT_TYPE)
        try:
            th = dht.read()
            temperature, humidity = th.temperature, th.humidity
        finally:
            dht.close()
    except Exception as err:
        print(f"  ⚠️  อ่านเซนเซอร์อุณหภูมิ (DHT) ไม่ได้ — ข้ามไปก่อน: {err}")

    return {
        "frame": frame,
        "image_path": image_path,
        "pm2_5": pm2_5,
        "pm1_0": pm1_0,
        "pm10": pm10,
        "temperature": temperature,
        "humidity": humidity,
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
def run_once(simulate: bool = False, model=None, model_kind: str | None = None):
    print(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] เริ่มเก็บข้อมูล 1 รอบ")

    raw = read_simulated() if simulate else read_hardware()

    # ค่าเซนเซอร์อาจไม่มีบางตัว (None) ในโหมดจริง — แสดงเป็น "—"
    def _fmt(v, nd=1):
        return f"{v:.{nd}f}" if v is not None else "—"
    print(f"  📷 ภาพ: {os.path.basename(raw['image_path'])}")
    print(f"  🌫️  PM2.5 จริง = {_fmt(raw['pm2_5'])} µg/m³ | "
          f"🌡️ {_fmt(raw['temperature'])}°C | 💧 {_fmt(raw['humidity'], 0)}%")

    # 3) เก็บลง Dataset (Ground Truth) — เฉพาะเมื่อมีค่าฝุ่นจริงไว้ใช้เทรน
    features = None
    if raw["frame"] is not None:
        features = extract_features(raw["frame"])
    if raw["pm2_5"] is not None:
        dataset.append_sample(
            image_path=raw["image_path"],
            pm2_5=raw["pm2_5"], pm1_0=raw["pm1_0"], pm10=raw["pm10"],
            temperature=raw["temperature"], humidity=raw["humidity"],
            features=features,
        )

    # 4) ถ้ามีโมเดล -> AI วิเคราะห์ภาพ (+ เทียบกับค่าจริงถ้ามี)
    #    Edge Impulse ทำนายจาก "ภาพ" โดยตรง / scikit-learn ทำนายจาก "ฟีเจอร์"
    predicted = None
    pred = None
    if model is not None:
        if model_kind == "edge_impulse" and raw["frame"] is not None:
            pred = model.predict(raw["frame"])
        elif model_kind == "sklearn" and features is not None:
            pred = model.predict(features)
    if pred is not None:
        predicted = pred.as_dict()
        msg = (f"  🤖 AI ประเมิน = {pred.pm25:.1f} µg/m³ "
               f"({pred.haze}, เชื่อมั่น {pred.confidence:.0f}%)")
        if raw["pm2_5"] is not None:
            msg += f" | ต่างจากค่าจริง {abs(pred.pm25 - raw['pm2_5']):.1f}"
        print(msg)

    # ค่าที่จะแสดงบน Dashboard: ใช้ค่าที่ AI ประเมินก่อน, ถ้าไม่มีโมเดลใช้ค่าเซนเซอร์
    if predicted:
        display_pm25 = predicted["pm25"]
    elif raw["pm2_5"] is not None:
        display_pm25 = round(raw["pm2_5"], 1)
    else:
        display_pm25 = 0.0            # ไม่มีทั้งโมเดลและเซนเซอร์
    cat = air_quality_category(display_pm25)

    def _num_or_blank(v, nd=1):
        return round(v, nd) if v is not None else ""   # "" -> backend เก็บเป็นค่าว่าง

    payload = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "station_id": config.STATION_ID,
        "pm2_5": display_pm25,
        "pm2_5_sensor": _num_or_blank(raw["pm2_5"]),   # ค่าจริงจาก PMS5003 (ถ้ามี)
        "temperature": _num_or_blank(raw["temperature"]),
        "humidity": _num_or_blank(raw["humidity"], 0),
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

    # โหลดโมเดลถ้ามี (Edge Impulse .eim ก่อน, ไม่มีก็ scikit-learn .joblib)
    model, model_kind = load_model()
    if model is None:
        print("ยังไม่มีโมเดล AI — จะเก็บ Dataset และแสดงค่าจากเซนเซอร์ไปก่อน")
        print("• เทรนบน Pi:  python train.py  (ได้ไฟล์ .joblib)")
        print("• หรือใช้ Edge Impulse: วางไฟล์ .eim ที่ device/data/pm25-model.eim")

    if args.once:
        run_once(simulate=args.simulate, model=model, model_kind=model_kind)
        return

    print(f"เริ่มทำงานแบบวนลูป (ทุก {args.interval} วินาที) — กด Ctrl+C เพื่อหยุด")
    try:
        while True:
            try:
                run_once(simulate=args.simulate, model=model, model_kind=model_kind)
            except Exception as err:
                print(f"  ❌ เกิดข้อผิดพลาดในรอบนี้: {err}")
            time.sleep(args.interval)
    except KeyboardInterrupt:
        print("\nหยุดการทำงานแล้ว")


if __name__ == "__main__":
    main()

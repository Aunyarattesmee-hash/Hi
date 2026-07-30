# -*- coding: utf-8 -*-
"""
collector.py — ตัวสั่งงานหลัก: อ่านเซนเซอร์ + ถ่ายภาพ + ดูระดับฝุ่นควัน แล้วเก็บลงฐานข้อมูล

มี 2 โหมด (เลือกที่ config.USE_MOCK):
  USE_MOCK = True   -> สร้างข้อมูลปลอมไว้ทดสอบ (ไม่ต้องมีเซนเซอร์)
  USE_MOCK = False  -> อ่านจากเซนเซอร์จริงบน Raspberry Pi 5

รันไฟล์นี้เดี่ยว ๆ (กด Run ใน Thonny) = จะวนอ่านค่าแล้วเก็บลง pm25.db ไปเรื่อย ๆ
ปกติเราจะไม่รันไฟล์นี้ตรง ๆ แต่ให้ app.py เรียกใช้ (มีเว็บให้ดูด้วย)
"""

import random
import time

import config


def read_mock():
    """สร้างข้อมูลจำลอง 1 ชุด (ไว้ทดสอบตอนยังไม่ต่อเซนเซอร์)"""
    from haze import LEVEL_NONE, LEVEL_MODERATE, LEVEL_HEAVY

    pm2_5 = round(random.uniform(5, 120), 1)   # สุ่มค่าฝุ่น
    # ให้ระดับฝุ่นควันสอดคล้องกับตัวเลข (เฉพาะโหมดจำลอง)
    if pm2_5 < 25:
        haze = LEVEL_NONE
    elif pm2_5 < 75:
        haze = LEVEL_MODERATE
    else:
        haze = LEVEL_HEAVY

    return {
        "pm2_5": pm2_5,
        "pm10": round(pm2_5 * 1.4, 1),
        "temperature": round(random.uniform(25, 35), 1),
        "humidity": round(random.uniform(50, 90), 1),
        "haze": haze,
        "image": None,   # โหมดจำลองไม่มีภาพจริง
    }


def read_real():
    """อ่านจากเซนเซอร์จริง 1 ชุด (ใช้บน Raspberry Pi 5 ที่ต่ออุปกรณ์ครบ)"""
    from sensors.pms3003 import PMS3003
    from sensors.dht22 import DHT22
    from camera import SkyCamera
    import haze

    # 1) อ่านค่าฝุ่นจาก PMS3003
    with PMS3003(config.PMS3003_PORT, config.PMS3003_BAUD) as pms:
        dust = pms.read()

    # 2) อ่านอุณหภูมิ/ความชื้นจาก DHT22
    dht = DHT22(config.DHT22_PIN)
    try:
        th = dht.read()
    finally:
        dht.close()

    # 3) ถ่ายภาพท้องฟ้า แล้วให้ AI ดูระดับฝุ่นควันจากภาพ
    cam = SkyCamera(config.CAMERA_INDEX, config.CAMERA_WIDTH, config.CAMERA_HEIGHT)
    image_path = cam.capture()
    haze_result = haze.classify_image(image_path)

    return {
        "pm2_5": dust["pm2_5"],
        "pm10": dust["pm10"],
        "temperature": th["temperature"],
        "humidity": th["humidity"],
        "haze": haze_result["level"],
        # เก็บเฉพาะชื่อไฟล์ (ไม่เอา path เต็ม) เพื่อให้เว็บเปิดดูได้
        "image": image_path.split("/")[-1],
    }


def read_once():
    """อ่านข้อมูล 1 ชุด — เลือกโหมดจริง/จำลองตาม config.USE_MOCK"""
    return read_mock() if config.USE_MOCK else read_real()


def collect_forever(db, interval=None):
    """
    วนอ่านค่าแล้วเก็บลงฐานข้อมูลไปเรื่อย ๆ (ใช้โดย app.py ในเบื้องหลัง)
    """
    interval = interval or config.READ_INTERVAL
    while True:
        try:
            d = read_once()
            db.insert(d["pm2_5"], d["pm10"], d["temperature"],
                      d["humidity"], d["haze"], d["image"])
            print("บันทึก: PM2.5=%.1f | %s | %.1f°C %.0f%%"
                  % (d["pm2_5"], d["haze"], d["temperature"], d["humidity"]))
        except Exception as e:
            print("รอบนี้อ่านค่าไม่สำเร็จ:", e)
        time.sleep(interval)


# ---- รันไฟล์นี้เดี่ยว ๆ = เก็บข้อมูลอย่างเดียว (ไม่มีเว็บ) ----
if __name__ == "__main__":
    from database import Database
    db = Database(config.DB_FILE)
    print("เริ่มเก็บข้อมูล (โหมดจำลอง)" if config.USE_MOCK else "เริ่มเก็บข้อมูลจากเซนเซอร์จริง")
    print("กดปุ่ม Stop สีแดงใน Thonny เพื่อหยุด")
    collect_forever(db)

#!/usr/bin/env python3
"""
อ่านค่าฝุ่นจากเซนเซอร์ Plantower PMS3003 แบบสแตนด์อโลน
รันได้ทันทีบน Raspberry Pi:  python3 read_pms3003.py

PMS3003 ส่งข้อมูลผ่าน UART เป็น frame ยาว 24 ไบต์ (baud 9600) รูปแบบ:
    ไบต์ 0-1   : start bytes 0x42 0x4d
    ไบต์ 2-3   : frame length = 20 (ความยาวส่วนที่เหลือ)
    ไบต์ 4-5   : PM1.0  (CF=1, standard particle)
    ไบต์ 6-7   : PM2.5  (CF=1)
    ไบต์ 8-9   : PM10   (CF=1)
    ไบต์ 10-11 : PM1.0  (atmospheric)  <- ใช้ค่านี้เป็นค่าจริงในอากาศ
    ไบต์ 12-13 : PM2.5  (atmospheric)
    ไบต์ 14-15 : PM10   (atmospheric)
    ไบต์ 16-21 : reserved
    ไบต์ 22-23 : checksum (ผลรวมไบต์ 0-21)

การต่อสาย (Raspberry Pi 5):
    VCC -> 5V  (pin 2)      GND -> GND (pin 6)
    TX  -> Pi RXD GPIO15 (pin 10)
    RX  -> Pi TXD GPIO14 (pin 8)
เปิด serial:  sudo raspi-config -> Interface Options -> Serial Port
             (ปิด login shell, เปิด hardware serial) แล้ว reboot
"""
from __future__ import annotations

import os
import struct
import sys
import time

try:
    import serial  # pyserial
except ImportError:
    print("ไม่พบไลบรารี pyserial — ติดตั้งด้วย:  pip install pyserial", file=sys.stderr)
    sys.exit(1)

PORT = os.getenv("PMS3003_PORT", "/dev/serial0")
BAUD = int(os.getenv("PMS3003_BAUD", "9600"))
FRAME_LEN = 24          # PMS3003 = 24 ไบต์เสมอ
BODY_LEN = 20           # ค่าในไบต์ length ของ PMS3003


def read_frame(ser: "serial.Serial", timeout: float = 3.0) -> bytes | None:
    """หา start bytes (0x42 0x4d) แล้วอ่าน frame ให้ครบ 24 ไบต์"""
    start = time.time()
    while time.time() - start < timeout:
        b = ser.read(1)
        if b != b"\x42":
            continue
        if ser.read(1) != b"\x4d":
            continue
        len_bytes = ser.read(2)
        if len(len_bytes) != 2 or struct.unpack(">H", len_bytes)[0] != BODY_LEN:
            continue                       # ไม่ใช่ frame ของ PMS3003
        body = ser.read(BODY_LEN)          # 18 ไบต์ข้อมูล + 2 ไบต์ checksum
        if len(body) == BODY_LEN:
            return b"\x42\x4d" + len_bytes + body
    return None


def valid_checksum(frame: bytes) -> bool:
    return sum(frame[:-2]) == struct.unpack(">H", frame[-2:])[0]


def parse(frame: bytes) -> dict[str, int]:
    """คืนค่า PM แบบ atmospheric (µg/m³) ซึ่งเป็นค่าจริงในอากาศ"""
    vals = struct.unpack(">6H", frame[4:16])
    return {"pm1_0": vals[3], "pm2_5": vals[4], "pm10": vals[5]}


def aqi_level(pm25: int) -> str:
    """แปลค่า PM2.5 เป็นระดับคุณภาพอากาศ (เกณฑ์ กรมควบคุมมลพิษ)"""
    if pm25 <= 15:
        return "ดีมาก 🟦"
    if pm25 <= 25:
        return "ดี 🟩"
    if pm25 <= 37:
        return "ปานกลาง 🟨"
    if pm25 <= 75:
        return "เริ่มมีผลต่อสุขภาพ 🟧"
    return "มีผลต่อสุขภาพ 🟥"


def main() -> None:
    print(f"เปิดพอร์ต {PORT} @ {BAUD} baud ...")
    try:
        ser = serial.Serial(PORT, BAUD, timeout=3.0)
    except serial.SerialException as e:
        print(f"เปิดพอร์ตไม่สำเร็จ: {e}", file=sys.stderr)
        print("ตรวจว่าเปิด serial ใน raspi-config แล้ว และต่อสาย TX/RX ถูกด้าน", file=sys.stderr)
        sys.exit(1)

    time.sleep(1.0)
    ser.reset_input_buffer()
    print("เริ่มอ่านค่า (กด Ctrl+C เพื่อหยุด)\n")

    try:
        while True:
            frame = read_frame(ser)
            if frame is None:
                print("อ่าน frame ไม่ทันเวลา — ลองใหม่ ...")
                continue
            if not valid_checksum(frame):
                print("checksum ผิด — ข้าม frame นี้")
                continue
            r = parse(frame)
            print(
                f"PM1.0={r['pm1_0']:>3} µg/m³   "
                f"PM2.5={r['pm2_5']:>3} µg/m³   "
                f"PM10={r['pm10']:>3} µg/m³   "
                f"| {aqi_level(r['pm2_5'])}"
            )
            time.sleep(1.0)
    except KeyboardInterrupt:
        print("\nหยุดการอ่านค่า")
    finally:
        ser.close()


if __name__ == "__main__":
    main()

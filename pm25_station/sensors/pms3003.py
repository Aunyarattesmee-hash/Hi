# -*- coding: utf-8 -*-
"""
pms3003.py — อ่านค่าฝุ่นจากเซนเซอร์ Plantower PMS3003 ผ่าน UART

PMS3003 ส่งข้อมูลออกมาเรื่อย ๆ เป็นชุด (frame) ยาว 24 ไบต์
  ไบต์ 0-1  : หัว frame คงที่ = 0x42 0x4d
  ไบต์ 2-3  : ความยาวส่วนที่เหลือ (= 20)
  ไบต์ 4-15 : ค่าฝุ่น 6 ค่า (PM1.0/PM2.5/PM10 แบบ CF=1 และแบบ atmospheric)
  ไบต์ 22-23: checksum (ผลรวมไบต์ทั้งหมดก่อนหน้า ไว้เช็คว่าข้อมูลไม่เพี้ยน)

ค่าที่เราสนใจคือ PM2.5 แบบ atmospheric (อยู่ที่ไบต์ 12-13)

การต่อสายกับ Raspberry Pi 5:
    PMS3003 VCC  -> 5V         (pin 2)
    PMS3003 GND  -> GND        (pin 6)
    PMS3003 TX   -> Pi RXD/GPIO15 (pin 10)
    PMS3003 RX   -> Pi TXD/GPIO14 (pin 8)

ก่อนใช้ต้องเปิด UART ก่อน:  sudo raspi-config
    -> Interface Options -> Serial Port
    -> "login shell over serial?"  ตอบ No
    -> "serial port hardware enabled?"  ตอบ Yes  แล้ว reboot
"""

import struct
import time

try:
    import serial  # ไลบรารี pyserial (ติดตั้ง: pip install pyserial)
except ImportError:
    serial = None


class PMS3003:
    """อ่านค่าฝุ่นจาก PMS3003"""

    def __init__(self, port, baud=9600, timeout=3.0):
        if serial is None:
            raise RuntimeError("ยังไม่ได้ติดตั้ง pyserial — สั่ง: pip install pyserial")
        self.port = port
        self.baud = baud
        self.timeout = timeout
        self._ser = None

    def open(self):
        """เปิดพอร์ต UART"""
        self._ser = serial.Serial(self.port, self.baud, timeout=self.timeout)
        time.sleep(1.0)               # รอให้เซนเซอร์พร้อม
        self._ser.reset_input_buffer()  # ล้างข้อมูลเก่าทิ้ง

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()

    def _read_frame(self):
        """หาไบต์หัว 0x42 0x4d แล้วอ่านทั้ง frame (24 ไบต์) กลับมา"""
        ser = self._ser
        start = time.time()
        while time.time() - start < self.timeout:
            b = ser.read(1)
            if b != b"\x42":            # ยังไม่เจอไบต์แรก
                continue
            if ser.read(1) != b"\x4d":  # ไบต์ที่สองไม่ตรง -> ข้าม
                continue
            body = ser.read(22)         # อ่านที่เหลืออีก 22 ไบต์ (รวมเป็น 24)
            if len(body) == 22:
                return b"\x42\x4d" + body
        return None

    @staticmethod
    def _checksum_ok(frame):
        """เช็คว่า checksum ถูกต้องไหม (ข้อมูลไม่เพี้ยน)"""
        total = sum(frame[:-2])                      # รวมทุกไบต์ ยกเว้น 2 ไบต์สุดท้าย
        expected = struct.unpack(">H", frame[-2:])[0]  # 2 ไบต์สุดท้าย = ค่าที่ควรจะเป็น
        return total == expected

    def read(self, retries=5):
        """
        อ่านค่า 1 ครั้ง คืนค่าเป็น dict เช่น
            {"pm1_0": 5.0, "pm2_5": 12.0, "pm10": 18.0}
        ถ้าอ่านพลาดจะลองซ้ำสูงสุด retries ครั้ง
        """
        if self._ser is None or not self._ser.is_open:
            self.open()

        for _ in range(retries):
            frame = self._read_frame()
            if frame and self._checksum_ok(frame):
                # ไบต์ 4-15 = 6 ค่า ตัวละ 2 ไบต์ (big-endian)
                v = struct.unpack(">6H", frame[4:16])
                # v[3]=PM1.0, v[4]=PM2.5, v[5]=PM10 (แบบ atmospheric)
                return {
                    "pm1_0": float(v[3]),
                    "pm2_5": float(v[4]),
                    "pm10": float(v[5]),
                }
        raise IOError("อ่านค่า PMS3003 ไม่สำเร็จ (ลองเช็คสาย TX/RX และ UART)")

    # ทำให้ใช้กับ with ... as ... ได้
    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()


# ---- ทดสอบไฟล์นี้เดี่ยว ๆ: กด Run ใน Thonny แล้วดูค่าฝุ่น ----
if __name__ == "__main__":
    import config
    with PMS3003(config.PMS3003_PORT, config.PMS3003_BAUD) as pms:
        for _ in range(5):
            print(pms.read())
            time.sleep(2)

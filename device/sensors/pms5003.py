"""
อ่านค่าจากเซนเซอร์ฝุ่น PMS5003 (Plantower) ผ่าน UART

PMS5003 ส่งข้อมูลเป็น frame ขนาด 32 ไบต์ ขึ้นต้นด้วย 0x42 0x4d
ให้ค่า PM1.0 / PM2.5 / PM10 ทั้งแบบ CF=1 (มาตรฐานโรงงาน) และ atmospheric

การต่อสาย (Raspberry Pi 5):
    PMS5003 VCC  -> 5V   (pin 2)
    PMS5003 GND  -> GND  (pin 6)
    PMS5003 TX   -> Pi RXD GPIO15 (pin 10)
    PMS5003 RX   -> Pi TXD GPIO14 (pin 8)
เปิด serial ด้วย: sudo raspi-config -> Interface Options -> Serial Port
(ปิด login shell, เปิด hardware serial)
"""
from __future__ import annotations

import struct
import time
from dataclasses import dataclass, asdict

try:
    import serial  # pyserial
except ImportError:  # ให้ import ผ่านบนเครื่องที่ยังไม่ได้ติดตั้ง (เช่น เครื่อง dev)
    serial = None


@dataclass
class PMReading:
    pm1_0: float          # µg/m³ (atmospheric)
    pm2_5: float          # µg/m³ (atmospheric) — ค่านี้คือ Ground Truth ที่เราใช้
    pm10: float           # µg/m³ (atmospheric)

    def as_dict(self):
        return asdict(self)


class PMS5003:
    START_BYTES = b"\x42\x4d"
    FRAME_LEN = 32

    def __init__(self, port: str, baudrate: int = 9600, timeout: float = 3.0):
        if serial is None:
            raise RuntimeError(
                "ไม่พบไลบรารี pyserial — ติดตั้งด้วย: pip install pyserial"
            )
        self.port = port
        self.baudrate = baudrate
        self.timeout = timeout
        self._ser = None

    def open(self):
        self._ser = serial.Serial(self.port, self.baudrate, timeout=self.timeout)
        # ล้าง buffer เก่าทิ้ง
        time.sleep(1.0)
        self._ser.reset_input_buffer()

    def close(self):
        if self._ser and self._ser.is_open:
            self._ser.close()

    def _read_frame(self) -> bytes | None:
        """หา start bytes แล้วอ่าน frame ที่เหลือ 30 ไบต์"""
        ser = self._ser
        # หาไบต์เริ่มต้น 0x42
        start = time.time()
        while time.time() - start < self.timeout:
            b = ser.read(1)
            if not b:
                continue
            if b == b"\x42":
                nxt = ser.read(1)
                if nxt == b"\x4d":
                    rest = ser.read(self.FRAME_LEN - 2)
                    if len(rest) == self.FRAME_LEN - 2:
                        return self.START_BYTES + rest
        return None

    @staticmethod
    def _validate(frame: bytes) -> bool:
        """ตรวจสอบ checksum (ผลรวมไบต์ 0..29 == ค่าใน 2 ไบต์สุดท้าย)"""
        if len(frame) != PMS5003.FRAME_LEN:
            return False
        checksum = sum(frame[:30])
        expected = struct.unpack(">H", frame[30:32])[0]
        return checksum == expected

    def read(self, retries: int = 5) -> PMReading:
        """อ่านค่า 1 ครั้ง (พยายามซ้ำหาก frame เสีย)"""
        if self._ser is None or not self._ser.is_open:
            self.open()
        for _ in range(retries):
            frame = self._read_frame()
            if frame and self._validate(frame):
                # ไบต์ 4..15 เป็น 6 ค่า uint16 big-endian
                # 0:PM1.0(CF1) 1:PM2.5(CF1) 2:PM10(CF1)
                # 3:PM1.0(atm) 4:PM2.5(atm) 5:PM10(atm)
                vals = struct.unpack(">6H", frame[4:16])
                return PMReading(
                    pm1_0=float(vals[3]),
                    pm2_5=float(vals[4]),
                    pm10=float(vals[5]),
                )
        raise IOError("อ่านค่า PMS5003 ไม่สำเร็จ (checksum ผิดพลาดทุกครั้ง)")

    def __enter__(self):
        self.open()
        return self

    def __exit__(self, *exc):
        self.close()


if __name__ == "__main__":
    # ทดสอบอ่านค่าจริงจากเซนเซอร์
    from config import PMS5003_PORT, PMS5003_BAUD

    with PMS5003(PMS5003_PORT, PMS5003_BAUD) as sensor:
        for _ in range(5):
            print(sensor.read())
            time.sleep(2)

"""
อ่านค่าจากเซนเซอร์ฝุ่น Plantower ผ่าน UART
รองรับทั้ง PMS5003 (frame 32 ไบต์) และ PMS3003 (frame 24 ไบต์) โดยอัตโนมัติ

ทุกรุ่นขึ้นต้นด้วย 0x42 0x4d ตามด้วยความยาว frame แล้วจึงเป็นค่า
PM1.0 / PM2.5 / PM10 ทั้งแบบ CF=1 และ atmospheric (ตำแหน่งเดียวกันทั้งสองรุ่น)
โค้ดนี้อ่านความยาว frame จากตัวข้อมูลเอง จึงใช้ได้กับทั้ง PMS3003 และ PMS5003

การต่อสาย (Raspberry Pi 5):
    VCC  -> 5V   (pin 2)
    GND  -> GND  (pin 6)
    TX   -> Pi RXD GPIO15 (pin 10)
    RX   -> Pi TXD GPIO14 (pin 8)
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
        """
        หา start bytes (0x42 0x4d) แล้วอ่านความยาว frame จากตัวข้อมูลเอง
        รองรับทั้ง PMS3003 (length=20 -> รวม 24 ไบต์) และ PMS5003 (length=28 -> รวม 32 ไบต์)
        """
        ser = self._ser
        start = time.time()
        while time.time() - start < self.timeout:
            b = ser.read(1)
            if not b:
                continue
            if b == b"\x42":
                nxt = ser.read(1)
                if nxt == b"\x4d":
                    len_bytes = ser.read(2)          # ไบต์ 2-3 = ความยาวส่วนที่เหลือ
                    if len(len_bytes) != 2:
                        continue
                    body_len = struct.unpack(">H", len_bytes)[0]
                    # กันค่าเพี้ยน (PMS3003=20, PMS5003=28)
                    if body_len not in (20, 28):
                        continue
                    body = ser.read(body_len)        # ข้อมูล + checksum
                    if len(body) == body_len:
                        return self.START_BYTES + len_bytes + body
        return None

    @staticmethod
    def _validate(frame: bytes) -> bool:
        """ตรวจ checksum: ผลรวมทุกไบต์ ยกเว้น 2 ไบต์สุดท้าย == ค่าใน 2 ไบต์สุดท้าย"""
        if len(frame) < 24:
            return False
        checksum = sum(frame[:-2])
        expected = struct.unpack(">H", frame[-2:])[0]
        return checksum == expected

    def read(self, retries: int = 5) -> PMReading:
        """อ่านค่า 1 ครั้ง (พยายามซ้ำหาก frame เสีย) — ใช้ได้ทั้ง PMS3003/PMS5003"""
        if self._ser is None or not self._ser.is_open:
            self.open()
        for _ in range(retries):
            frame = self._read_frame()
            if frame and self._validate(frame):
                # ไบต์ 4..15 เป็น 6 ค่า uint16 big-endian (ตำแหน่งเดียวกันทั้งสองรุ่น)
                # 0:PM1.0(CF1) 1:PM2.5(CF1) 2:PM10(CF1)
                # 3:PM1.0(atm) 4:PM2.5(atm) 5:PM10(atm)
                vals = struct.unpack(">6H", frame[4:16])
                return PMReading(
                    pm1_0=float(vals[3]),
                    pm2_5=float(vals[4]),
                    pm10=float(vals[5]),
                )
        raise IOError("อ่านค่าเซนเซอร์ฝุ่นไม่สำเร็จ (checksum ผิดพลาดทุกครั้ง)")

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

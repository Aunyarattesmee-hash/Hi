"""
อ่านค่าอุณหภูมิ (°C) และความชื้นสัมพัทธ์ (%RH) จากเซนเซอร์ DHT22 (AM2302)

ใช้ไลบรารี adafruit-circuitpython-dht

การต่อสาย (Raspberry Pi 5):
    DHT22 VCC  -> 3.3V (pin 1)
    DHT22 DATA -> GPIO4 (pin 7)  + ตัวต้านทาน pull-up 10kΩ ระหว่าง DATA กับ VCC
    DHT22 GND  -> GND  (pin 9)

หมายเหตุ: DHT22 อ่านค่าได้ทุก ~2 วินาที และบางครั้งอ่านพลาด (RuntimeError)
เป็นเรื่องปกติของเซนเซอร์ตัวนี้ จึงมีการ retry ให้
"""
from __future__ import annotations

import time
from dataclasses import dataclass, asdict

try:
    import board
    import adafruit_dht
except (ImportError, NotImplementedError):
    board = None
    adafruit_dht = None


@dataclass
class THReading:
    temperature: float   # °C
    humidity: float      # %RH

    def as_dict(self):
        return asdict(self)


class DHT22:
    """
    รองรับทั้ง DHT22 และ DHT11 (เลือกด้วยพารามิเตอร์ sensor_type)
    การต่อสายเหมือนกันทั้งสองรุ่น — ต่างแค่ชิปข้างใน
    """
    def __init__(self, pin_name: str = "D4", sensor_type: str = "DHT22"):
        if adafruit_dht is None or board is None:
            raise RuntimeError(
                "ไม่พบไลบรารี adafruit-circuitpython-dht — "
                "ติดตั้งด้วย: pip install adafruit-circuitpython-dht"
            )
        pin = getattr(board, pin_name, None)
        if pin is None:
            raise ValueError(f"ไม่รู้จักขา GPIO ชื่อ '{pin_name}' (ตัวอย่างที่ถูกต้อง: D4)")
        sensor_type = (sensor_type or "DHT22").upper()
        DeviceClass = adafruit_dht.DHT11 if sensor_type == "DHT11" else adafruit_dht.DHT22
        # use_pulseio=False เสถียรกว่าบน Raspberry Pi 5
        self._dev = DeviceClass(pin, use_pulseio=False)

    def read(self, retries: int = 5, delay: float = 2.0) -> THReading:
        last_err = None
        for _ in range(retries):
            try:
                t = self._dev.temperature
                h = self._dev.humidity
                if t is not None and h is not None:
                    return THReading(temperature=float(t), humidity=float(h))
            except RuntimeError as err:
                # อ่านพลาดชั่วคราว — ลองใหม่
                last_err = err
            time.sleep(delay)
        raise IOError(f"อ่านค่า DHT22 ไม่สำเร็จ: {last_err}")

    def close(self):
        try:
            self._dev.exit()
        except Exception:
            pass


if __name__ == "__main__":
    from config import DHT22_PIN, DHT_TYPE

    dev = DHT22(DHT22_PIN, DHT_TYPE)
    try:
        for _ in range(5):
            print(dev.read())
            time.sleep(2)
    finally:
        dev.close()

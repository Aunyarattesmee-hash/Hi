# -*- coding: utf-8 -*-
"""
dht22.py — อ่านอุณหภูมิ / ความชื้น จากเซนเซอร์ DHT22 (AM2302) ผ่าน GPIO

การต่อสายกับ Raspberry Pi 5:
    DHT22 VCC  -> 3.3V   (pin 1)
    DHT22 DATA -> GPIO4  (pin 7)   *ต่อ R 10kΩ ระหว่าง VCC กับ DATA (pull-up)
    DHT22 GND  -> GND    (pin 9)

ติดตั้งไลบรารีก่อนใช้:
    pip install adafruit-circuitpython-dht
    sudo apt install libgpiod2
"""


class DHT22:
    """อ่านอุณหภูมิ/ความชื้นจาก DHT22"""

    def __init__(self, pin_name="D4"):
        import board
        import adafruit_dht

        pin = getattr(board, pin_name)          # แปลง "D4" -> board.D4
        # use_pulseio=False ทำงานเสถียรกว่าบน Raspberry Pi 5
        self._dht = adafruit_dht.DHT22(pin, use_pulseio=False)

    def read(self, retries=3):
        """
        อ่านค่า 1 ครั้ง คืน dict เช่น {"temperature": 29.5, "humidity": 68.0}
        DHT22 อ่านพลาดได้บ่อย จึงลองซ้ำหลายรอบ
        """
        last_err = None
        for _ in range(retries):
            try:
                t = self._dht.temperature
                h = self._dht.humidity
                if t is not None and h is not None:
                    return {
                        "temperature": round(float(t), 1),
                        "humidity": round(float(h), 1),
                    }
            except RuntimeError as e:
                last_err = e   # DHT22 พลาดบ่อย เป็นเรื่องปกติ ลองใหม่ได้
        raise IOError("อ่านค่า DHT22 ไม่สำเร็จ: %s" % last_err)

    def close(self):
        try:
            self._dht.exit()
        except Exception:
            pass


# ---- ทดสอบไฟล์นี้เดี่ยว ๆ ----
if __name__ == "__main__":
    import time
    import config
    dht = DHT22(config.DHT22_PIN)
    try:
        for _ in range(5):
            print(dht.read())
            time.sleep(2)
    finally:
        dht.close()

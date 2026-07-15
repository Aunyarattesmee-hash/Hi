# อธิบายวิธีการเขียนโค้ด + โค้ดจริง
## ระบบติดตามและประเมินค่าฝุ่น PM2.5 ด้วย AI (Raspberry Pi 5)

เอกสารนี้อธิบาย **วิธีคิด/วิธีเขียนโค้ด** ของแต่ละส่วน พร้อม **โค้ดจริง** ที่ใช้งาน
เพื่อประกอบรายงาน/การนำเสนอโครงงาน

---

## 1. ภาพรวมและโครงสร้างโปรเจกต์

ระบบแบ่งเป็น 3 ส่วนหลัก ทำงานร่วมกัน:

```
device/     → โค้ดฝั่งอุปกรณ์ (อ่านเซนเซอร์ + กล้อง + AI)  รันบน Raspberry Pi 5
backend/    → หลังบ้าน (เว็บเซิร์ฟเวอร์ + ฐานข้อมูล)  Python Flask + SQLite
frontend/   → หน้าบ้าน (หน้าเว็บ Dashboard)  HTML + CSS + JavaScript
```

**หลักการ:** เมื่อฝุ่น PM2.5 สูง ท้องฟ้าจะมีหมอกควันมาก ทำให้ภาพขุ่น สีฟ้าจางลง
เราจึงเขียนโค้ดให้ AI เรียนรู้ความสัมพันธ์ "ภาพท้องฟ้า → ค่า PM2.5" โดยใช้ค่าจริง
จากเซนเซอร์ PMS5003 เป็นค่าเฉลย (Ground Truth)

---

## 2. การตั้งค่ากลาง — `device/config.py`

**วิธีเขียน:** แยกค่าคงที่ทั้งหมด (พอร์ต, ขา GPIO, รอบเวลา) ไว้ที่เดียว
เพื่อแก้ไขง่าย และรองรับการตั้งค่าผ่าน environment variable

```python
import os

# เซนเซอร์ฝุ่น PMS5003 ต่อผ่าน UART
PMS5003_PORT = os.getenv("PMS5003_PORT", "/dev/serial0")
PMS5003_BAUD = 9600

# เซนเซอร์ DHT22 ต่อกับ GPIO4
DHT22_PIN = os.getenv("DHT22_PIN", "D4")

# กล้อง USB (Logitech C270)
CAMERA_INDEX = 0
CAMERA_WIDTH, CAMERA_HEIGHT = 1280, 720

# รอบการอ่านค่า (วินาที)
SAMPLE_INTERVAL_SEC = 300   # ทุก 5 นาที
```

---

## 3. อ่านค่าฝุ่นจาก PMS5003 — `device/sensors/pms5003.py`

**วิธีเขียน:** PMS5003 ส่งข้อมูลเป็นชุด (frame) ขนาด 32 ไบต์ ขึ้นต้นด้วย `0x42 0x4d`
เราเขียนโค้ดให้: (1) หาไบต์เริ่มต้น (2) อ่านครบ 32 ไบต์ (3) ตรวจ checksum (4) แกะค่า PM2.5 ออกมา

```python
import struct, serial

class PMS5003:
    FRAME_LEN = 32

    def __init__(self, port, baudrate=9600):
        self._ser = serial.Serial(port, baudrate, timeout=3.0)

    def read(self):
        # หาไบต์เริ่มต้น 0x42 0x4d
        while True:
            if self._ser.read(1) == b"\x42" and self._ser.read(1) == b"\x4d":
                frame = b"\x42\x4d" + self._ser.read(30)
                break
        # ตรวจ checksum ว่าข้อมูลถูกต้อง
        checksum = sum(frame[:30])
        expected = struct.unpack(">H", frame[30:32])[0]
        if checksum != expected:
            raise IOError("ข้อมูลผิดพลาด")
        # แกะค่า PM1.0 / PM2.5 / PM10 (หน่วย µg/m³)
        vals = struct.unpack(">6H", frame[4:16])
        return {"pm1_0": vals[3], "pm2_5": vals[4], "pm10": vals[5]}
```

> **จุดสำคัญ:** ค่า `pm2_5` คือค่าฝุ่นจริงที่ใช้เป็น "ค่าเฉลย" ในการเทรน AI

---

## 4. อ่านอุณหภูมิ/ความชื้นจาก DHT22 — `device/sensors/dht22.py`

**วิธีเขียน:** ใช้ไลบรารี `adafruit_dht` DHT22 บางครั้งอ่านพลาดเป็นเรื่องปกติ
จึงเขียนให้ **ลองซ้ำ (retry)** หลายครั้ง

```python
import adafruit_dht, board, time

class DHT22:
    def __init__(self, pin_name="D4"):
        self._dev = adafruit_dht.DHT22(getattr(board, pin_name), use_pulseio=False)

    def read(self, retries=5):
        for _ in range(retries):
            try:
                t = self._dev.temperature
                h = self._dev.humidity
                if t is not None and h is not None:
                    return {"temperature": t, "humidity": h}
            except RuntimeError:
                pass          # อ่านพลาดชั่วคราว ลองใหม่
            time.sleep(2)
        raise IOError("อ่าน DHT22 ไม่สำเร็จ")
```

---

## 5. ถ่ายภาพท้องฟ้า — `device/camera.py`

**วิธีเขียน:** ใช้ OpenCV เปิดกล้อง USB อ่านทิ้งไม่กี่เฟรมแรกเพื่อให้กล้องปรับแสง
แล้วบันทึกภาพเป็นไฟล์ `.jpg`

```python
import cv2, time, os
from datetime import datetime

class SkyCamera:
    def __init__(self, index=0, width=1280, height=720):
        self.index, self.width, self.height = index, width, height

    def capture(self):
        cap = cv2.VideoCapture(self.index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        for _ in range(5):            # อ่านทิ้งให้กล้องปรับแสง
            ok, frame = cap.read()
            time.sleep(0.1)
        cap.release()
        path = f"data/images/sky_{datetime.now():%Y%m%d_%H%M%S}.jpg"
        cv2.imwrite(path, frame)
        return frame, path
```

---

## 6. โมเดล AI ประเมินค่าฝุ่น — `device/model.py`

**วิธีเขียน (แนวคิด):** แทนที่จะใช้ Deep Learning หนัก ๆ เราสกัด "ฟีเจอร์หมอกควัน"
จากภาพ 11 ค่า (ความสว่าง, ความอิ่มตัวสี, ความคมชัด, Dark Channel ฯลฯ) แล้วเทรน
โมเดล **Gradient Boosting** ให้เดาค่า PM2.5 — เบา รันบน Pi ได้ ไม่ต้องใช้ GPU

**6.1 สกัดฟีเจอร์จากภาพ:**
```python
import cv2, numpy as np

def extract_features(image):
    img = cv2.resize(image, (256, 256))
    b, g, r = cv2.split(img.astype(np.float32))
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    s, v = hsv[:, :, 1], hsv[:, :, 2]
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    dark_channel = np.min(img.astype(np.float32), axis=2)   # ตัวชี้วัดหมอก
    return np.array([
        r.mean(), g.mean(), b.mean(),
        s.mean(), s.std(), v.mean(), v.std(),
        gray.std(),                    # ความคมชัด (contrast)
        dark_channel.mean(),           # ยิ่งหมอกเยอะ ยิ่งสว่าง
        b.mean() / (r.mean() + 1e-6),  # อัตราส่วนฟ้า/แดง
    ], dtype=np.float32)
```

**6.2 เทรนโมเดล:**
```python
from sklearn.ensemble import GradientBoostingRegressor
from sklearn.metrics import mean_absolute_error

def train(X, y):                       # X = ฟีเจอร์ภาพ, y = ค่า PM2.5 จริง
    model = GradientBoostingRegressor(n_estimators=300, max_depth=3,
                                      learning_rate=0.05)
    model.fit(X, y)
    return model
```

**6.3 แปลงค่าเป็นระดับหมอกควัน:**
```python
def haze_level(pm25):
    if pm25 <= 25:  return "น้อย"
    if pm25 <= 50:  return "ปานกลาง"
    return "มาก"
```

---

## 7. โปรแกรมหลัก (วนลูป) — `device/collector.py`

**วิธีเขียน:** รวมทุกอย่างเป็นลูปเดียวตามผังงาน — ถ่ายภาพ → อ่านเซนเซอร์ →
เก็บ Dataset → AI ประเมิน → ส่งขึ้น Backend

```python
def read_hardware():
    from camera import SkyCamera
    from sensors.pms5003 import PMS5003
    from sensors.dht22 import DHT22

    frame, image_path = SkyCamera().capture()       # 1) ถ่ายภาพ
    with PMS5003(config.PMS5003_PORT) as pms:
        pm = pms.read()                             # 2) อ่านฝุ่นจริง
    dht = DHT22(config.DHT22_PIN)
    th = dht.read(); dht.close()                    # 3) อ่านอุณหภูมิ/ความชื้น
    return {"frame": frame, "image_path": image_path,
            "pm2_5": pm["pm2_5"], "temperature": th["temperature"],
            "humidity": th["humidity"]}

def run_once(model):
    raw = read_hardware()
    features = extract_features(raw["frame"])
    dataset.append_sample(...)                      # 4) เก็บลง Dataset
    if model:
        pred = model.predict(features)              # 5) AI ประเมินค่า
    push_to_backend(payload, raw["image_path"])     # 6) ส่งขึ้นหลังบ้าน
```

---

## 8. หลังบ้าน (Backend) — `backend/app.py`

**วิธีเขียน:** ใช้ Flask สร้าง REST API — รับข้อมูลจาก Pi และส่งข้อมูลให้หน้าเว็บ

```python
from flask import Flask, jsonify, request
import database

app = Flask(__name__)

# รับข้อมูล + รูป จาก Raspberry Pi
@app.post("/api/readings")
def ingest_reading():
    if request.headers.get("X-API-Key") != API_KEY:   # ตรวจรหัสลับ
        abort(401)
    f = request.files["image"]                        # รับไฟล์รูป
    f.save(os.path.join(UPLOAD_DIR, image_filename))
    database.insert_reading({                          # เก็บลงฐานข้อมูล
        "pm2_5": float(request.form["pm2_5"]),
        "temperature": float(request.form["temperature"]),
        "humidity": float(request.form["humidity"]),
        ...
    })
    return jsonify({"status": "ok"}), 201

# ส่งค่าล่าสุดให้หน้าเว็บ
@app.get("/api/latest")
def api_latest():
    return jsonify(database.get_latest())
```

**ฐานข้อมูล SQLite** (`backend/database.py`) — เก็บทุกการวัดในตาราง `readings`:
```python
CREATE TABLE readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT, pm2_5 REAL, temperature REAL, humidity REAL,
    haze TEXT, confidence REAL, image_filename TEXT
);
```

---

## 9. หน้าบ้าน (Dashboard) — `frontend/`

**วิธีเขียน:** HTML สร้างโครงหน้า, CSS จัดหน้าตา, JavaScript ดึงข้อมูลจาก Backend
มาแสดง (ค่า PM2.5, กราฟ, ตาราง) และวาดกราฟด้วย Canvas เอง (ไม่พึ่งไลบรารีภายนอก
จึงทำงานแบบออฟไลน์บน Pi ได้)

```javascript
// ดึงค่าล่าสุดจากหลังบ้านมาแสดงบนการ์ด
async function loadLatest() {
  const d = await fetch('/api/latest').then(r => r.json());
  document.getElementById('pmValue').textContent = d.pm2_5;
  document.getElementById('tempValue').textContent = d.temperature;
  document.getElementById('humValue').textContent = d.humidity;
}
setInterval(loadLatest, 30000);   // อัปเดตทุก 30 วินาที
```

---

## 10. วิธีรันโปรแกรม

```bash
# ครั้งเดียวจบ — ติดตั้ง + เปิดเว็บ + เก็บข้อมูล
./run.sh --simulate     # โหมดทดสอบ (ไม่มีเซนเซอร์)
./run.sh                # โหมดจริง (ต่อเซนเซอร์ครบ)

# เทรนโมเดล AI (เมื่อเก็บข้อมูลพอ)
python train.py
```

เปิด Dashboard ที่ `http://<ip-ของ-pi>:8000`

---

## สรุปเทคโนโลยีที่ใช้

| ส่วน | ภาษา/เครื่องมือ |
|------|-----------------|
| อ่านเซนเซอร์ | Python + pyserial + adafruit-dht |
| ประมวลผลภาพ | OpenCV (cv2) + NumPy |
| โมเดล AI | scikit-learn (Gradient Boosting) |
| หลังบ้าน | Flask + SQLite |
| หน้าบ้าน | HTML + CSS + JavaScript (Canvas) |

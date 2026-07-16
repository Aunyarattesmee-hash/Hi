# 🚀 เริ่มตรงนี้ — คู่มือครบตั้งแต่ต่ออุปกรณ์เสร็จ → ระบบทำงานจริง
## ระบบติดตามและประเมินค่าฝุ่น PM2.5 ด้วย AI (Raspberry Pi 5)

คู่มือเดียวจบ: การรันจริง + โค้ดการทำงาน + วิธีเอาโมเดลที่เทรนใส่โค้ด + เว็บไซต์

---

# ส่วนที่ 1 — หลังต่ออุปกรณ์เสร็จ ทำอะไรต่อ

ต่ออุปกรณ์แล้ว (PMS + DHT22 + กล้อง) ทำ 3 ขั้นนี้:

### ขั้น 1: เปิด UART (ครั้งเดียว — ให้เซนเซอร์ฝุ่นทำงาน)
```bash
sudo raspi-config
```
→ `3 Interface Options` → `I6 Serial Port` → login shell = **No** → hardware = **Yes** → Finish → รีสตาร์ท

### ขั้น 2: รันทั้งระบบ (คำสั่งเดียว)
```bash
cd ~/Documents/PM25AIMonitor*
./run.sh
```
> `./run.sh` = อ่านเซนเซอร์จริง | `./run.sh --simulate` = ข้อมูลจำลอง (ทดสอบ)

### ขั้น 3: เปิด Dashboard
เปิดเบราว์เซอร์ → `http://<ip-ของ-pi>:8000` (หา ip ด้วย `hostname -I`)

---

# ส่วนที่ 2 — โค้ดการทำงานจริง (สั่งเครื่องวัดยังไง)

**ไฟล์หลัก: `device/collector.py`** — วนลูปวัดค่าทุกรอบ

```python
def read_hardware():
    from camera import SkyCamera
    from sensors.pms5003 import PMS5003
    from sensors.dht22 import DHT22

    frame, image_path = SkyCamera().capture()      # 1) กล้องถ่ายภาพท้องฟ้า
    with PMS5003(config.PMS5003_PORT) as pms:
        pm = pms.read()                            # 2) วัดค่าฝุ่น PM2.5 จริง
    dht = DHT22(config.DHT22_PIN, config.DHT_TYPE)
    th = dht.read()                                # 3) วัดอุณหภูมิ + ความชื้น
    return {"frame": frame, "image_path": image_path,
            "pm2_5": pm.pm2_5, "temperature": th.temperature,
            "humidity": th.humidity}

def run_once(model):
    raw = read_hardware()                          # วัดค่า 1 รอบ
    features = extract_features(raw["frame"])      # สกัดลักษณะจากภาพ
    dataset.append_sample(...)                     # 4) เก็บลง Dataset
    if model:
        pred = model.predict(features)             # 5) AI ประเมินค่าจากภาพ
    push_to_backend(payload, raw["image_path"])    # 6) ส่งขึ้นเว็บ
```

**สั่งให้วนซ้ำทุก ๆ กี่นาที** (`config.py`):
```python
SAMPLE_INTERVAL_SEC = 300   # วัดทุก 5 นาที
```

**สั่งว่าใช้ขาไหน** (`config.py`):
```python
PMS5003_PORT = "/dev/serial0"   # เซนเซอร์ฝุ่น = ขา 8,10 (UART)
DHT22_PIN    = "D4"             # DHT22 = ขา 7 (GPIO4)
CAMERA_INDEX = 0                # กล้อง USB
```

---

# ส่วนที่ 3 — เอาโมเดลที่เทรนแล้ว "ใส่ในโค้ด" ยังไง

## 🔑 หัวใจ: โค้ดเชื่อมกับโมเดลผ่าน "ไฟล์" ไม่ต้องก๊อปโค้ดไปแปะ

```
เทรน  →  ได้ไฟล์โมเดล  →  โค้ดโหลดไฟล์เอง  →  ใช้ทำนาย
```

## วิธี A — เทรนบน Pi ด้วย train.py (ง่ายสุด)

**1) เก็บข้อมูลก่อน** — รัน `./run.sh` ให้กล้อง+เซนเซอร์เก็บภาพคู่ค่าฝุ่นจริงสักพัก
(เก็บที่ `device/data/dataset.csv` + `device/data/images/`)

**2) เทรน:**
```bash
cd ~/Documents/PM25AIMonitor*/device
python train.py
```
→ ได้ไฟล์โมเดล `device/data/pm25_model.joblib`

**3) โค้ดโหลดโมเดลให้อัตโนมัติ** (`collector.py`) — ไม่ต้องแก้อะไร:
```python
if PM25Model.exists(config.MODEL_PATH):
    model = PM25Model.load(config.MODEL_PATH)   # ← มีไฟล์โมเดล → โหลดมาใช้เลย
    print("โหลดโมเดล AI แล้ว")
else:
    print("ยังไม่มีโมเดล — ใช้ค่าเซนเซอร์ไปก่อน")
```

> **แค่วางไฟล์ `pm25_model.joblib` ไว้ที่ `device/data/` โค้ดก็หยิบไปใช้เอง**

## วิธี B — เทรนบน Edge Impulse (ถ้าจำเป็นต้องใช้)

> ⚠️ โปรเจกต์ต้องเป็นแบบ **Image Classification** (แบ่งภาพเป็นกลุ่ม เช่น เห็นภูเขาชัด/เล็กน้อย/ไม่เห็น)
> ไม่ใช่ Object Detection

**1) โหลดโมเดลลง Pi** (ผ่าน Edge Impulse CLI):
```bash
edge-impulse-linux-runner --download model.eim
mv model.eim ~/Documents/PM25AIMonitor*/device/data/pm25-model.eim
```

**2) โค้ดที่ใช้โมเดล .eim** (`edge_impulse/ei_inference.py`):
```python
from edge_impulse_linux.image import ImageImpulseRunner

class EdgeImpulsePM25:
    def __init__(self, model_path):
        self.runner = ImageImpulseRunner(model_path)   # ← โหลดไฟล์ .eim
        self.runner.init()

    def predict(self, frame):
        features, _ = self.runner.get_features_from_image(frame)
        res = self.runner.classify(features)           # ← ให้โมเดลจำแนกภาพ
        # แปลงผลเป็นระดับฝุ่น น้อย/ปานกลาง/มาก
        return res
```

---

# ส่วนที่ 4 — เว็บไซต์ (Dashboard)

## หลังบ้าน (`backend/app.py`) — Flask รับ+ส่งข้อมูล
```python
@app.post("/api/readings")        # รับข้อมูล+รูปจาก Pi → เก็บลงฐานข้อมูล
@app.get("/api/latest")           # ส่งค่าล่าสุดให้หน้าเว็บ
@app.get("/api/trend")            # ส่งข้อมูลกราฟ
@app.get("/api/history")          # ส่งประวัติ
```

## หน้าบ้าน (`frontend/app.js`) — ดึงข้อมูลมาแสดง
```javascript
async function loadLatest() {
  const d = await fetch('/api/latest').then(r => r.json());
  document.getElementById('pmValue').textContent   = d.pm2_5;      // การ์ด PM2.5
  document.getElementById('tempValue').textContent = d.temperature; // อุณหภูมิ
  document.getElementById('humValue').textContent  = d.humidity;    // ความชื้น
}
setInterval(loadLatest, 30000);   // อัปเดตทุก 30 วินาที
```

## ไฟล์เว็บไซต์
- `frontend/index.html` — โครงหน้า (การ์ด, กราฟ, ตาราง)
- `frontend/styles.css` — หน้าตา
- `frontend/app.js` — ดึงข้อมูล + วาดกราฟ

---

# สรุปคำสั่งทั้งหมด (Copy ไปใช้ได้เลย)

```bash
# 1) เปิด UART (ครั้งเดียว)
sudo raspi-config          # Interface → Serial → No → Yes → รีสตาร์ท

# 2) เข้าโฟลเดอร์
cd ~/Documents/PM25AIMonitor*

# 3) รันทั้งระบบ (เว็บ + เก็บข้อมูล + AI)
./run.sh                   # เซนเซอร์จริง
#   หรือ ./run.sh --simulate   (ทดสอบ ไม่มีเซนเซอร์)

# 4) เทรนโมเดล AI (เมื่อเก็บข้อมูลพอ)
cd device && python train.py

# 5) เปิดเว็บ:  http://<ip-pi>:8000   (หา ip: hostname -I)
```

---

## แผนที่ไฟล์สำคัญ
| ไฟล์ | หน้าที่ |
|------|---------|
| `device/collector.py` | โปรแกรมหลัก วัดค่า+ส่งขึ้นเว็บ |
| `device/sensors/pms5003.py` | อ่านฝุ่น PMS |
| `device/sensors/dht22.py` | อ่านอุณหภูมิ/ความชื้น |
| `device/camera.py` | ถ่ายภาพ |
| `device/model.py` + `train.py` | AI + เทรน |
| `device/data/pm25_model.joblib` | **ไฟล์โมเดลที่เทรนแล้ว (โค้ดโหลดเอง)** |
| `backend/app.py` | เว็บเซิร์ฟเวอร์ + ฐานข้อมูล |
| `frontend/` | หน้าเว็บ Dashboard |

# ระบบติดตามและประเมินค่าฝุ่น PM2.5 ด้วย AI
### AI-based Air Quality Monitoring System (Raspberry Pi 5)

ระบบถ่ายภาพท้องฟ้าด้วยกล้อง Webcam แล้วใช้โมเดล AI ประเมินค่าฝุ่น **PM2.5**
จากลักษณะ "หมอกควัน" ในภาพ โดยเทียบเคียงกับค่าจริงจากเซนเซอร์ **PMS5003**
พร้อมแสดงผลบน Dashboard เว็บแบบเรียลไทม์ (ตามรูปที่ 1 และรูปที่ 2)

---

## 🧩 อุปกรณ์ (Hardware)

| อุปกรณ์ | หน้าที่ |
|---------|---------|
| Raspberry Pi 5 | ประมวลผลหลัก เก็บข้อมูล รันโมเดล AI + เว็บเซิร์ฟเวอร์ |
| Logitech C270 Webcam | ถ่ายภาพท้องฟ้า (USB) |
| PMS5003 | วัดค่า PM2.5 จริง (Ground Truth) ผ่าน UART |
| DHT22 (AM2302) | วัดอุณหภูมิ / ความชื้น ผ่าน GPIO |
| Micro SD Card | เก็บ Dataset (ภาพ + ค่าเซนเซอร์) และฐานข้อมูล |
| USB-C PD Power | จ่ายไฟ Raspberry Pi 5 |

### การต่อสาย
```
PMS5003   VCC→5V(pin2)  GND→GND(pin6)  TX→GPIO15/RXD(pin10)  RX→GPIO14/TXD(pin8)
DHT22     VCC→3.3V(pin1) DATA→GPIO4(pin7) + pull-up 10kΩ     GND→GND(pin9)
C270      เสียบ USB (จะเป็น /dev/video0)
```
เปิด UART: `sudo raspi-config` → Interface Options → Serial Port
(ปิด login shell, เปิด hardware serial) และติดตั้ง `sudo apt install libgpiod2`

---

## 🔄 หลักการทำงาน (ตามรูปที่ 1)

```
เริ่มต้น
  → Webcam ถ่ายภาพท้องฟ้า
  → PMS5003 + DHT22 วัด PM2.5 / อุณหภูมิ / ความชื้น จริง (Ground Truth)
  → Raspberry Pi 5 เก็บภาพ + ข้อมูลเซนเซอร์ ลง Dataset
  → AI Model Training: เรียนรู้ความสัมพันธ์ ภาพท้องฟ้า ↔ ค่า PM2.5
  → ภาพใหม่ → AI วิเคราะห์ → Model Evaluation
  → ผ่านเกณฑ์? ── No ──→ เพิ่มข้อมูล Train ใหม่ (วนกลับ Dataset)
              └─ Yes ──→ Deploy Model → เปรียบเทียบกับค่า PM2.5 จริง
  → แสดงผล: PM2.5, ระดับหมอกควัน, ค่าความเชื่อมั่น (%) บน Dashboard
```

---

## 📁 โครงสร้างโปรเจกต์

```
Hi/
├── device/                 # โค้ดฝั่งอุปกรณ์ (รันบน Raspberry Pi 5)
│   ├── config.py           # ตั้งค่ากลาง (พอร์ต, GPIO, รอบเวลา, backend)
│   ├── camera.py           # ถ่ายภาพจากกล้อง C270
│   ├── sensors/
│   │   ├── pms5003.py      # อ่านค่าฝุ่น PMS5003 (UART)
│   │   └── dht22.py        # อ่านอุณหภูมิ/ความชื้น DHT22
│   ├── model.py            # โมเดล AI (สกัดฟีเจอร์หมอก + Gradient Boosting)
│   ├── dataset.py          # จัดการ Dataset (CSV บน SD card)
│   ├── train.py            # เทรน + ประเมิน + Deploy โมเดล
│   ├── collector.py        # โปรแกรมหลัก วนลูปตามรูปที่ 1
│   └── requirements.txt
├── backend/                # หลังบ้าน (Flask + SQLite)
│   ├── app.py              # REST API + เสิร์ฟเว็บ/รูป
│   ├── database.py         # ชั้นฐานข้อมูล SQLite
│   └── requirements.txt
├── frontend/               # หน้าบ้าน (Dashboard ตามรูปที่ 2)
│   ├── index.html
│   ├── styles.css
│   ├── app.js              # วาดกราฟด้วย Canvas เอง (ไม่พึ่ง CDN, ทำงาน offline)
│   └── assets/no-image.svg
└── deploy/                 # systemd service สำหรับรันอัตโนมัติ
    ├── pm25-collector.service
    └── pm25-backend.service
```

---

## 🚀 วิธีติดตั้งและใช้งาน

### 1) เตรียมสภาพแวดล้อม
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt
pip install -r device/requirements.txt      # บน Raspberry Pi
```

### 2) รัน Backend (หลังบ้าน + Dashboard)
```bash
export BACKEND_API_KEY="ตั้งรหัสลับของคุณ"
cd backend
python app.py                                # dev  → http://localhost:8000
# โปรดักชัน: gunicorn -w 2 -b 0.0.0.0:8000 app:app
```
เปิดเบราว์เซอร์ไปที่ `http://<ip-ของ-pi>:8000`

### 3) เก็บข้อมูลด้วยอุปกรณ์จริง
```bash
export BACKEND_URL="http://localhost:8000"
export BACKEND_API_KEY="ตั้งรหัสลับของคุณ"   # ต้องตรงกับ backend
cd device
python collector.py                          # วนลูปทุก 5 นาที (ปรับใน config)
```

### 4) เทรนโมเดล AI (เมื่อเก็บข้อมูลได้พอ ~หลายสิบ–ร้อยตัวอย่าง)
```bash
cd device
python train.py     # เทรน → ประเมิน MAE → ถ้าผ่านเกณฑ์จะ Deploy อัตโนมัติ
```
หลังจากมีไฟล์โมเดลแล้ว `collector.py` จะใช้ AI ประเมินค่าและส่งขึ้น Dashboard

### 🧪 ทดสอบระบบโดยไม่มีฮาร์ดแวร์ (โหมดจำลอง)
```bash
cd device
python collector.py --simulate --once    # สร้างภาพ+ค่าเซนเซอร์จำลอง 1 รอบ
python collector.py --simulate           # วนลูปจำลองต่อเนื่อง
```
ใช้ทดสอบ backend + frontend ได้ทันทีก่อนติดตั้งอุปกรณ์จริง

---

## 🖥️ หน้าเว็บ Dashboard (ตามรูปที่ 2)

- **การ์ด PM2.5** — ค่าที่ AI ประเมิน + ระดับคุณภาพอากาศ + แถบสีมาตรฐาน
- **Image (Webcam)** — ภาพท้องฟ้าล่าสุด (Live) พร้อมเวลา
- **Temperature / Humidity** — อุณหภูมิ / ความชื้นจาก DHT22
- **Trend** — กราฟแนวโน้ม (วันนี้ / 7 วัน / 30 วัน) พร้อมแถบสีคุณภาพอากาศ
- **History** — ตารางประวัติข้อมูลล่าสุด (เวลา, PM2.5, อุณหภูมิ, ความชื้น, ภาพ)
- **Data Export** — ดาวน์โหลดข้อมูลทั้งหมดเป็น CSV

---

## 🔌 REST API

| Method | Endpoint | คำอธิบาย |
|--------|----------|----------|
| POST | `/api/readings` | รับข้อมูล+ภาพจาก Pi (ต้องมี header `X-API-Key`) |
| GET | `/api/latest` | ค่าล่าสุด + ค่าเฉลี่ยรายวัน/สัปดาห์ |
| GET | `/api/trend?range=today\|7d\|30d` | ข้อมูลกราฟแนวโน้ม |
| GET | `/api/history?limit=N` | ประวัติข้อมูล |
| GET | `/api/export.csv` | ส่งออกข้อมูลทั้งหมด (CSV) |
| GET | `/api/image/<file>` · `/api/latest-image` | ภาพจากกล้อง |

---

## 🧠 โมเดล AI (สรุป)

เมื่อ PM2.5 สูง ท้องฟ้าจะมีหมอกควันมาก ทำให้ความอิ่มตัวสี/ความคมชัดลดลง และ
Dark Channel สว่างขึ้น ระบบสกัดฟีเจอร์เหล่านี้ 11 ตัวจากภาพ แล้วเทรน
**Gradient Boosting Regressor** (scikit-learn) เรียนรู้ความสัมพันธ์
`ฟีเจอร์ภาพ → ค่า PM2.5 จริง` — เบา รันบน CPU ของ Pi 5 ได้ ไม่ต้องใช้ GPU
ค่าความเชื่อมั่นประเมินจากความสอดคล้องของ ensemble

> เกณฑ์ผ่าน: `MAE ≤ 8 µg/m³` (ปรับได้ที่ `MODEL_MAE_THRESHOLD` ใน config)

---

## ⚙️ รันอัตโนมัติเมื่อเปิดเครื่อง (systemd)
```bash
sudo cp deploy/pm25-backend.service /etc/systemd/system/
sudo cp deploy/pm25-collector.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now pm25-backend pm25-collector
```

# คู่มือติดตั้งลง Raspberry Pi 5 (ตั้งแต่ต้นจนใช้งานได้)

ทำตามลำดับนี้บน Raspberry Pi 5 (Raspberry Pi OS 64-bit, Bookworm)

---

## 1) เตรียม Raspberry Pi OS
- แฟลช **Raspberry Pi OS (64-bit)** ลง Micro SD ด้วย Raspberry Pi Imager
- ตั้งค่า Wi-Fi / SSH / ชื่อผู้ใช้ (`pi`) ตอนแฟลชได้เลย
- เสียบ SD, ต่อไฟ **USB-C PD**, เปิดเครื่อง แล้ว SSH เข้า:
```bash
ssh pi@<ip-ของ-pi>
sudo apt update && sudo apt full-upgrade -y
```

## 2) เปิดพอร์ตและติดตั้งไลบรารีระบบ
```bash
# เปิด Serial (UART) สำหรับ PMS5003
sudo raspi-config
#   -> Interface Options -> Serial Port
#   -> "login shell over serial?"  = No
#   -> "serial port hardware enabled?" = Yes
#   แล้ว Finish และ reboot

# ไลบรารีที่เซนเซอร์/กล้อง/โมเดลต้องใช้
sudo apt install -y python3-venv python3-pip git libgpiod2 libatlas-base-dev
```

## 3) ต่อสายอุปกรณ์ (ปิดไฟ Pi ก่อนต่อ)
```
PMS5003  VCC→5V(pin2)  GND→GND(pin6)  TX→GPIO15/RXD(pin10)  RX→GPIO14/TXD(pin8)
DHT22    VCC→3.3V(pin1) DATA→GPIO4(pin7) + ตัวต้านทาน 10kΩ (DATA↔VCC)  GND→GND(pin9)
C270     เสียบพอร์ต USB  (จะเป็น /dev/video0)
```

## 4) ดึงโค้ดลงเครื่อง
```bash
cd ~
git clone <URL-ของ-repo-นี้> Hi
cd Hi
git checkout claude/raspberry-pi-sensor-web-9g775x
```
> ถ้าไม่มีเน็ตที่ Pi ใช้ `scp -r Hi pi@<ip>:~/` จากคอมพิวเตอร์แทนได้

## 5) สร้าง virtualenv + ติดตั้งไลบรารี Python
```bash
cd ~/Hi
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r backend/requirements.txt
pip install -r device/requirements.txt
```

## 6) ตั้งค่ารหัสลับ (ให้ฝั่ง Pi กับ Backend ตรงกัน)
```bash
export BACKEND_API_KEY="ตั้งรหัสของคุณเอง"
export BACKEND_URL="http://localhost:8000"
```

## 7) ทดสอบทีละส่วน (สำคัญ — เช็กก่อนรันจริง)
```bash
source ~/Hi/.venv/bin/activate
cd ~/Hi/device
python -c "from config import *; ensure_dirs(); print('config OK')"
python sensors/pms5003.py     # ควรพิมพ์ค่า PM ออกมา
python sensors/dht22.py       # ควรพิมพ์อุณหภูมิ/ความชื้น
python camera.py              # ถ่ายภาพ 1 รูป บอก path ที่บันทึก
```
ถ้าตัวไหน error ให้เช็กสายและข้อ 2 ก่อน

## 8) รัน Backend + Dashboard
เปิด terminal ที่ 1:
```bash
source ~/Hi/.venv/bin/activate
export BACKEND_API_KEY="รหัสเดียวกับข้อ 6"
cd ~/Hi/backend
python app.py            # http://<ip-ของ-pi>:8000
```
เปิดเบราว์เซอร์ (คอม/มือถือในวง LAN เดียวกัน) ไปที่ `http://<ip-ของ-pi>:8000`

## 9) รันตัวเก็บข้อมูล
เปิด terminal ที่ 2:
```bash
source ~/Hi/.venv/bin/activate
export BACKEND_API_KEY="รหัสเดียวกับข้อ 6"
export BACKEND_URL="http://localhost:8000"
cd ~/Hi/device
python collector.py --once     # ทดสอบ 1 รอบก่อน
python collector.py            # วนลูปเก็บข้อมูลต่อเนื่อง
```
> ยังไม่มีโมเดลตอนแรก ระบบจะแสดงค่าจากเซนเซอร์และค่อย ๆ สะสม Dataset

## 10) เทรนโมเดล AI (เมื่อเก็บข้อมูลพอ)
```bash
cd ~/Hi/device
python train.py     # ผ่านเกณฑ์แล้วจะ Deploy โมเดลอัตโนมัติ
```
จากนั้น `collector.py` จะใช้ AI ประเมินค่าให้เอง
(หรือเทรนบน Edge Impulse — ดู `edge_impulse/README.md`)

## 11) ตั้งให้รันอัตโนมัติเมื่อเปิดเครื่อง (systemd)
แก้ path/User ในไฟล์ `deploy/*.service` ให้ตรงเครื่องก่อน แล้ว:
```bash
sudo cp ~/Hi/deploy/pm25-backend.service /etc/systemd/system/
sudo cp ~/Hi/deploy/pm25-collector.service /etc/systemd/system/
# ใส่ BACKEND_API_KEY ในไฟล์ service ทั้งสอง (บรรทัด Environment=)
sudo systemctl daemon-reload
sudo systemctl enable --now pm25-backend pm25-collector

# ดูสถานะ/ล็อก
systemctl status pm25-backend pm25-collector
journalctl -u pm25-collector -f
```
ตอนนี้เปิด Pi เมื่อไหร่ ระบบจะทำงานเองและเปิด Dashboard ที่พอร์ต 8000

---

## ปัญหาที่พบบ่อย
| อาการ | วิธีแก้ |
|-------|---------|
| อ่าน PMS5003 ไม่ได้ | ยังไม่เปิด UART (ข้อ 2) หรือสลับ TX/RX |
| DHT22 อ่านพลาดบ่อย | ปกติของ DHT22 — โค้ด retry ให้แล้ว, ตรวจตัวต้านทาน pull-up |
| เปิดกล้องไม่ได้ | เช็ก `ls /dev/video*` และ `CAMERA_INDEX` ใน config |
| เข้าเว็บจากมือถือไม่ได้ | ต้องอยู่วง Wi-Fi เดียวกัน ใช้ IP ของ Pi (`hostname -I`) |
| ส่งข้อมูลขึ้น backend ไม่ได้ | `BACKEND_API_KEY` สองฝั่งต้องตรงกัน |

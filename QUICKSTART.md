# เริ่มต้นแบบมือใหม่ — กดอะไรก่อน-หลัง

ทำตามข้อ 1 → 8 ตามลำดับ ไม่ต้องข้าม

---

## 🖥️ ส่วน A — ลง Raspberry Pi OS (ทำบนคอมพิวเตอร์)

**1. โหลดโปรแกรม Raspberry Pi Imager**
- เข้า https://www.raspberrypi.com/software → กด **Download for Windows** (หรือ Mac)
- ติดตั้งแล้วเปิดโปรแกรม

**2. เสียบ Micro SD เข้าคอม แล้วในโปรแกรม Imager กด 3 ปุ่มนี้**
- กด **CHOOSE DEVICE** → เลือก **Raspberry Pi 5**
- กด **CHOOSE OS** → เลือก **Raspberry Pi OS (64-bit)**
- กด **CHOOSE STORAGE** → เลือก Micro SD ของเรา

**3. ตั้งค่าล่วงหน้า (สำคัญ) — กดรูปเฟือง ⚙️ (หรือกด NEXT → Edit Settings)**
- ✅ ตั้ง **hostname**: `raspberrypi`
- ✅ ตั้ง **username** = `pi` และ **password** (จำให้ได้)
- ✅ ใส่ชื่อ Wi-Fi + รหัส Wi-Fi (ใช้อันเดียวกับมือถือ/คอม)
- ✅ แท็บ Services → เปิด **Enable SSH** → เลือก "Use password authentication"
- กด **SAVE**

**4. กด WRITE → YES** แล้วรอจนเสร็จ (ประมาณ 5-10 นาที)
- เสร็จแล้วถอด SD ออก

---

## 🔌 ส่วน B — เปิดเครื่อง Pi

**5. ประกอบและเปิดเครื่อง**
- เสียบ Micro SD เข้า Raspberry Pi 5
- เสียบสายไฟ **USB-C PD** → เครื่องจะเปิดเอง (ไฟสีเขียวกะพริบ)
- รอ 1-2 นาที ให้ Pi ต่อ Wi-Fi

> 💡 อุปกรณ์เซนเซอร์ (PMS5003, DHT22, กล้อง) ค่อยต่อทีหลังในข้อ B ของ `deploy/SETUP_PI5.md`
> ตอนนี้ให้เปิดเครื่องเปล่า ๆ ให้เข้าได้ก่อน

---

## ⌨️ ส่วน C — เข้าไปสั่งงาน Pi (ทำบนคอม)

**6. เปิดโปรแกรมพิมพ์คำสั่ง**
- **Windows:** กดปุ่ม Start → พิมพ์ `cmd` → กด Enter (เปิด Command Prompt)
- **Mac:** เปิดโปรแกรม **Terminal**

**7. พิมพ์คำสั่งนี้เพื่อเข้า Pi** (แล้วกด Enter)
```bash
ssh pi@raspberrypi.local
```
- ถ้าถาม `Are you sure...?` พิมพ์ **yes** กด Enter
- ใส่ **password** ที่ตั้งไว้ข้อ 3 (พิมพ์แล้วจะไม่ขึ้นตัวอักษร เป็นเรื่องปกติ) กด Enter
- ถ้าเข้าได้ จะขึ้น `pi@raspberrypi:~ $` = สำเร็จ! 🎉

> ถ้า `raspberrypi.local` ไม่ติด ให้หา IP ของ Pi (เช่นจากหน้าเราเตอร์) แล้วใช้ `ssh pi@192.168.x.x`

---

## 🚀 ส่วน D — ติดตั้งและรันระบบ

### ⭐ วิธีง่ายสุด: สคริปต์เดียวจบ
ดึงโค้ดลงมาแล้ว (หรือแตก zip ไว้ที่ `~/Hi`) พิมพ์แค่นี้:
```bash
cd ~/Hi
export BACKEND_API_KEY="mysecret"   # ตั้งรหัสของคุณ
./run.sh --simulate                 # ครั้งแรกจะติดตั้งไลบรารีให้เอง แล้วเปิดทุกอย่าง
```
รอจนขึ้น `✅ ระบบทำงานแล้ว เปิด Dashboard ที่: http://<ip>:8000`
แล้วเปิดลิงก์นั้นในเบราว์เซอร์ (Wi-Fi เดียวกับ Pi) — จบ!
เมื่อต่อเซนเซอร์จริงแล้วให้รัน `./run.sh` (ตัด `--simulate` ออก)
กด **Ctrl+C** เพื่อหยุดทั้งระบบ

> ถ้าขึ้น `Permission denied` ให้พิมพ์ `chmod +x run.sh` ก่อนหนึ่งครั้ง

---

### หรือทำแบบละเอียดทีละคำสั่ง (ถ้าอยากเข้าใจแต่ละขั้น)

**8. ก๊อปวางคำสั่งชุดนี้ทีละบล็อก**

ติดตั้งของที่ต้องใช้:
```bash
sudo apt update && sudo apt install -y python3-venv git libgpiod2 libatlas-base-dev
```

ดึงโค้ดโปรเจกต์:
```bash
cd ~
git clone <ใส่-URL-repo-ของคุณ> Hi
cd Hi
git checkout claude/raspberry-pi-sensor-web-9g775x
```

ติดตั้งไลบรารี Python:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r backend/requirements.txt -r device/requirements.txt
```

ตั้งรหัสลับ (เปลี่ยนคำว่า mysecret เป็นรหัสของคุณ):
```bash
export BACKEND_API_KEY="mysecret"
```

**ลองรันแบบจำลองก่อน (ยังไม่ต้องต่อเซนเซอร์):**
```bash
# เปิดเว็บเซิร์ฟเวอร์ (ทำงานค้างไว้)
cd ~/Hi/backend && python app.py &
# กลับมาสร้างข้อมูลจำลอง 1 ชุด
cd ~/Hi/device && python collector.py --once --simulate
```

**9. เปิดดู Dashboard**
- หา IP ของ Pi: พิมพ์ `hostname -I` (ได้เลขเช่น 192.168.1.50)
- เปิดเบราว์เซอร์ในมือถือ/คอม (ต้องอยู่ Wi-Fi เดียวกับ Pi) พิมพ์:
  `http://192.168.1.50:8000`
- ควรเห็นหน้า Dashboard พร้อมข้อมูลจำลอง ✅

---

## ✅ ผ่านขั้นนี้แล้วค่อยไปต่อ
- **ต่อเซนเซอร์จริง** + ทดสอบทีละตัว → ดู `deploy/SETUP_PI5.md` ข้อ 3 และ 7
- **เก็บข้อมูลจริง + เทรน AI** → `deploy/SETUP_PI5.md` ข้อ 9-10
- **ให้เปิดเองอัตโนมัติ** → `deploy/SETUP_PI5.md` ข้อ 11

> ทั้งหมดนี้ยังไม่ต้องต่อเซนเซอร์ก็ทดสอบได้ด้วย `--simulate` — ให้ระบบเดินได้ก่อน แล้วค่อยเสียบอุปกรณ์จริงทีหลัง

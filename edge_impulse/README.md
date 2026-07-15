# เทรนโมเดล PM2.5 ด้วย Edge Impulse

ส่วนนี้ให้ทางเลือกในการเทรนโมเดล AI ประเมินค่า PM2.5 จากภาพท้องฟ้า
บนแพลตฟอร์ม **Edge Impulse** (แทน/เสริมโมเดล scikit-learn ใน `device/model.py`)
เหมาะกับการทำ Deep Learning บนภาพ และ deploy ลง Raspberry Pi 5 ได้ง่าย

## ไฟล์ในโฟลเดอร์นี้

| ไฟล์ | หน้าที่ |
|------|---------|
| `export_dataset.py` | เตรียมภาพ + label ลงโฟลเดอร์ `export/train`, `export/test` (ลากวางอัปโหลด) |
| `upload_images.py` | อัปโหลดภาพ + ค่า PM2.5 ขึ้น Edge Impulse โดยตรงผ่าน Ingestion API |
| `ei_inference.py` | รันโมเดล `.eim` ที่เทรนเสร็จบน Pi (อินเทอร์เฟซเดียวกับ `device/model.py`) |
| `requirements.txt` | ไลบรารีที่ต้องใช้ |

---

## ขั้นตอนทั้งหมด (End-to-End)

### 1. เก็บข้อมูลก่อน
เก็บภาพท้องฟ้าคู่กับค่า PM2.5 จริงจากเซนเซอร์ให้ได้จำนวนพอสมควร
(ยิ่งหลากหลายสภาพอากาศยิ่งดี — แนะนำ 200+ ภาพ)
```bash
cd device
python collector.py            # หรือ --simulate เพื่อทดสอบ
```
ข้อมูลจะอยู่ที่ `device/data/dataset.csv` และ `device/data/images/`

### 2. สร้างโปรเจกต์บน Edge Impulse
1. สมัคร/เข้าสู่ระบบ https://studio.edgeimpulse.com
2. **Create new project** → ตั้งชื่อ เช่น `pm25-sky`
3. ไปที่ **Dashboard → Keys** คัดลอก **API Key** (`ei_...`)

### 3. อัปโหลดข้อมูล (เลือกวิธีใดวิธีหนึ่ง)

**วิธี A — อัปโหลดตรงผ่าน API (แนะนำ):**
```bash
pip install -r edge_impulse/requirements.txt
export EI_API_KEY="ei_xxxxxxxx"
python edge_impulse/upload_images.py         # แบ่ง train/test 80/20 ให้อัตโนมัติ
```

**วิธี B — เตรียมไฟล์แล้วลากวาง:**
```bash
python edge_impulse/export_dataset.py
# ได้โฟลเดอร์ edge_impulse/export/train และ /test
# ชื่อไฟล์รูปแบบ  <PM2.5>.<ชื่อเดิม>.jpg  (Edge Impulse จะอ่าน label เป็นตัวเลขให้)
```
แล้วไปที่ Studio → **Data acquisition → Upload data** ลากโฟลเดอร์ train/test เข้าไป

> Edge Impulse จะใช้ค่า label (ตัวเลข PM2.5) เป็นเป้าหมายของ **Regression**

### 4. ออกแบบ Impulse
ไปที่ **Impulse design → Create impulse**
- **Input block:** Image (เช่น 96×96 หรือ 160×160, Resize mode: Fit shortest)
- **Processing block:** *Image* (สี RGB)
- **Learning block:** *Regression* (ทำนายค่าต่อเนื่อง = PM2.5)

กด **Save Impulse** → ไปที่ **Image** → *Generate features* →
ไปที่ **Regression** → ตั้ง epochs/learning rate → **Start training**

### 5. ตรวจผล
ดู **Regression → ผลลัพธ์** ค่า MAE / R² บนชุด validation
และหน้า **Model testing** เพื่อทดสอบกับชุด test (ควร MAE ต่ำ)

### 6. Deploy ลง Raspberry Pi 5
**วิธีที่ง่ายที่สุด (Edge Impulse for Linux):**
```bash
# บน Raspberry Pi 5
sudo apt install -y libatlas-base-dev
npm install -g edge-impulse-cli
pip install edge_impulse_linux

# ดาวน์โหลดโมเดลเป็นไฟล์ .eim
edge-impulse-linux-runner --download pm25-model.eim
mv pm25-model.eim device/data/
```
หรือไปที่ Studio → **Deployment → Linux (AARCH64)** เพื่อดาวน์โหลด `.eim`

### 7. ใช้งานโมเดล Edge Impulse ใน collector
`ei_inference.py` มีคลาส `EdgeImpulsePM25` ที่คืนผลแบบเดียวกับ `device/model.py`
ทดสอบเดี่ยว ๆ:
```bash
python edge_impulse/ei_inference.py device/data/images/sky_xxx.jpg
```
ผูกเข้ากับ `collector.py` ได้โดยแทนการโหลด `PM25Model` ด้วย `EdgeImpulsePM25`
(เมื่อพบไฟล์ `device/data/pm25-model.eim`) — ส่วนที่เหลือของ pipeline เหมือนเดิม

---

## สรุปสองทางเลือกของโมเดล

| | scikit-learn (`device/model.py`) | Edge Impulse (`edge_impulse/`) |
|--|--|--|
| วิธี | สกัดฟีเจอร์หมอก 11 ตัว + Gradient Boosting | Deep Learning บนภาพเต็ม |
| เทรน | บนเครื่อง/Pi (`train.py`) | บนคลาวด์ Edge Impulse Studio |
| ข้อดี | เบามาก ไม่ต้องต่อเน็ต ทำงานทันที | แม่นกว่าเมื่อข้อมูลเยอะ, UI จัดการง่าย |
| Deploy | ไฟล์ `.joblib` | ไฟล์ `.eim` |

เลือกใช้ได้ตามความเหมาะสม — โครงสร้าง collector รองรับทั้งสองแบบ

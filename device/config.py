"""
การตั้งค่ากลางของอุปกรณ์ตรวจวัด (Raspberry Pi 5)
ระบบติดตามและประเมินค่าฝุ่น PM2.5 ด้วย AI

แก้ไขค่าต่าง ๆ ในไฟล์นี้ให้ตรงกับการติดตั้งจริงของคุณ
สามารถ override ด้วย environment variable ได้ (ดู os.getenv ด้านล่าง)
"""
import os

# ---------------------------------------------------------------------------
# ข้อมูลสถานีตรวจวัด
# ---------------------------------------------------------------------------
STATION_NAME = os.getenv("STATION_NAME", "โรงเรียนปายวิทยาคาร อ.ปาย จ.แม่ฮ่องสอน")
STATION_ID = os.getenv("STATION_ID", "PAI-01")

# ---------------------------------------------------------------------------
# การเชื่อมต่อเซนเซอร์ (ปรับตามการต่อสายจริงบน Raspberry Pi 5)
# ---------------------------------------------------------------------------
# PMS5003 ต่อผ่าน UART -> เปิด serial port ใน raspi-config (/dev/ttyAMA0 หรือ /dev/serial0)
PMS5003_PORT = os.getenv("PMS5003_PORT", "/dev/serial0")
PMS5003_BAUD = int(os.getenv("PMS5003_BAUD", "9600"))

# เซนเซอร์อุณหภูมิ/ความชื้น ต่อกับ GPIO (ตัวอย่างใช้ GPIO4 = pin 7)
DHT22_PIN = os.getenv("DHT22_PIN", "D4")  # รูปแบบของไลบรารี adafruit-blinka เช่น D4, D17
# ชนิดเซนเซอร์: "DHT22" หรือ "DHT11" (การต่อสายเหมือนกัน ต่างแค่ชิป)
DHT_TYPE = os.getenv("DHT_TYPE", "DHT22").upper()

# กล้อง Logitech C270 (USB webcam) -> มักเป็น /dev/video0 (index 0)
CAMERA_INDEX = int(os.getenv("CAMERA_INDEX", "0"))
CAMERA_WIDTH = int(os.getenv("CAMERA_WIDTH", "1280"))
CAMERA_HEIGHT = int(os.getenv("CAMERA_HEIGHT", "720"))
# ตัดขอบล่างของภาพ (พื้น/อาคาร) ให้เหลือเฉพาะท้องฟ้า สัดส่วน 0.0-1.0 ของความสูง
SKY_CROP_TOP_RATIO = float(os.getenv("SKY_CROP_TOP_RATIO", "0.0"))
SKY_CROP_BOTTOM_RATIO = float(os.getenv("SKY_CROP_BOTTOM_RATIO", "0.55"))

# ---------------------------------------------------------------------------
# ที่เก็บข้อมูลบน Micro SD Card
# ---------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.getenv("DATA_DIR", os.path.join(BASE_DIR, "data"))
IMAGE_DIR = os.path.join(DATA_DIR, "images")          # ภาพท้องฟ้าที่ถ่าย
DATASET_CSV = os.path.join(DATA_DIR, "dataset.csv")   # dataset สำหรับเทรนโมเดล
MODEL_PATH = os.path.join(DATA_DIR, "pm25_model.joblib")   # โมเดล scikit-learn (เทรนบน Pi)
# โมเดลที่เทรนจาก Edge Impulse (Export เป็น Linux AARCH64 .eim แล้ววางไว้ที่นี่)
# ถ้ามีไฟล์นี้ collector.py จะใช้โมเดล Edge Impulse ก่อน (ทำนายจากภาพโดยตรง)
EIM_MODEL_PATH = os.getenv("EIM_MODEL_PATH", os.path.join(DATA_DIR, "pm25-model.eim"))

# ---------------------------------------------------------------------------
# รอบการทำงาน
# ---------------------------------------------------------------------------
# ระยะเวลาระหว่างการอ่านค่าแต่ละรอบ (วินาที) — mockup อัปเดตทุก ~5 นาที
SAMPLE_INTERVAL_SEC = int(os.getenv("SAMPLE_INTERVAL_SEC", "300"))

# เกณฑ์ผ่านการประเมินโมเดล (Mean Absolute Error สูงสุดที่ยอมรับได้ หน่วย µg/m³)
MODEL_MAE_THRESHOLD = float(os.getenv("MODEL_MAE_THRESHOLD", "8.0"))

# ---------------------------------------------------------------------------
# การส่งข้อมูลขึ้นเว็บ (Backend API)
# ---------------------------------------------------------------------------
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")
BACKEND_INGEST_ENDPOINT = f"{BACKEND_URL}/api/readings"
BACKEND_API_KEY = os.getenv("BACKEND_API_KEY", "changeme-secret-key")
# ถ้า True จะส่งข้อมูลขึ้น backend, ถ้า False เก็บลง SD card อย่างเดียว
PUSH_TO_BACKEND = os.getenv("PUSH_TO_BACKEND", "true").lower() == "true"


def ensure_dirs():
    """สร้างโฟลเดอร์เก็บข้อมูลถ้ายังไม่มี"""
    os.makedirs(IMAGE_DIR, exist_ok=True)

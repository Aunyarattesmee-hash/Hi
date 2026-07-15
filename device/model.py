"""
โมเดล AI ประเมินค่า PM2.5 จากภาพท้องฟ้า

แนวคิด: เมื่อค่าฝุ่น PM2.5 สูง ท้องฟ้าจะมี "หมอกควัน" (haze) มากขึ้น ทำให้
  - ความอิ่มตัวสี (saturation) ลดลง ฟ้าดูขาว/เทา
  - ความคมชัด (contrast) ลดลง
  - Dark Channel สว่างขึ้น (ค่า transmission ต่ำ ตามทฤษฎี dehazing)
  - ความสว่างรวมสูงขึ้น สีฟ้าจางลง

เราจึงสกัดฟีเจอร์เหล่านี้จากภาพ แล้วเทรน regressor (Gradient Boosting)
ให้เรียนรู้ความสัมพันธ์ ภาพท้องฟ้า -> ค่า PM2.5 จริง (Ground Truth จาก PMS5003)

วิธีนี้เบา รันได้บน Raspberry Pi 5 (CPU) ไม่ต้องใช้ deep learning/GPU
"""
from __future__ import annotations

import os
from dataclasses import dataclass

import numpy as np

try:
    import cv2
except ImportError:
    cv2 = None

try:
    import joblib
    from sklearn.ensemble import GradientBoostingRegressor
    from sklearn.model_selection import train_test_split
    from sklearn.metrics import mean_absolute_error
except ImportError:
    joblib = None


FEATURE_NAMES = [
    "mean_R", "mean_G", "mean_B",
    "mean_saturation", "std_saturation",
    "mean_value", "std_value",
    "contrast", "dark_channel_mean",
    "blue_red_ratio", "colorfulness",
]


# ---------------------------------------------------------------------------
# การสกัดฟีเจอร์จากภาพ
# ---------------------------------------------------------------------------
def extract_features(image) -> np.ndarray:
    """
    รับภาพ BGR (numpy array จาก OpenCV) คืน feature vector 1 มิติ
    """
    if cv2 is None:
        raise RuntimeError("ต้องติดตั้ง opencv-python เพื่อสกัดฟีเจอร์ภาพ")

    img = cv2.resize(image, (256, 256))
    b, g, r = cv2.split(img.astype(np.float32))

    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV).astype(np.float32)
    s = hsv[:, :, 1]
    v = hsv[:, :, 2]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)

    # Dark channel = ค่าต่ำสุดของ 3 ช่องสี ณ แต่ละพิกเซล (ตัวชี้วัดหมอก)
    dark_channel = np.min(img.astype(np.float32), axis=2)

    # Colorfulness (Hasler & Susstrunk)
    rg = r - g
    yb = 0.5 * (r + g) - b
    colorfulness = np.sqrt(rg.std() ** 2 + yb.std() ** 2) + \
        0.3 * np.sqrt(rg.mean() ** 2 + yb.mean() ** 2)

    features = [
        r.mean(), g.mean(), b.mean(),
        s.mean(), s.std(),
        v.mean(), v.std(),
        gray.std(),                       # contrast
        dark_channel.mean(),
        b.mean() / (r.mean() + 1e-6),     # อัตราส่วนฟ้า/แดง
        colorfulness,
    ]
    return np.array(features, dtype=np.float32)


def extract_features_from_path(path: str) -> np.ndarray:
    img = cv2.imread(path)
    if img is None:
        raise IOError(f"อ่านภาพไม่ได้: {path}")
    return extract_features(img)


# ---------------------------------------------------------------------------
# ระดับหมอกควัน / คุณภาพอากาศ (อ้างอิงเกณฑ์ AQI PM2.5 ของไทย)
# ---------------------------------------------------------------------------
def haze_level(pm25: float) -> str:
    """แปลงค่า PM2.5 เป็นระดับหมอกควัน (น้อย/ปานกลาง/มาก) ตามในรูปที่ 1"""
    if pm25 <= 25:
        return "น้อย"
    if pm25 <= 50:
        return "ปานกลาง"
    return "มาก"


def air_quality_category(pm25: float) -> dict:
    """
    แปลงค่า PM2.5 เป็นระดับคุณภาพอากาศ 5 ระดับ (ตามแถบสีในรูปที่ 2)
    คืน dict: label, color
    """
    if pm25 <= 15:
        return {"label": "คุณภาพอากาศดีมาก", "level": "very_good", "color": "#2e7d32"}
    if pm25 <= 25:
        return {"label": "คุณภาพอากาศดี", "level": "good", "color": "#9ccc65"}
    if pm25 <= 37.5:
        return {"label": "คุณภาพอากาศปานกลาง", "level": "moderate", "color": "#ffb300"}
    if pm25 <= 75:
        return {"label": "เริ่มมีผลต่อสุขภาพ", "level": "unhealthy", "color": "#fb8c00"}
    return {"label": "มีผลกระทบต่อสุขภาพ", "level": "hazardous", "color": "#e53935"}


# ---------------------------------------------------------------------------
# ผลการประเมิน
# ---------------------------------------------------------------------------
@dataclass
class Prediction:
    pm25: float          # ค่าที่ประเมินได้ µg/m³
    haze: str            # ระดับหมอกควัน น้อย/ปานกลาง/มาก
    confidence: float    # ค่าความเชื่อมั่น % (0-100)
    category: dict       # ระดับคุณภาพอากาศ (label/color)

    def as_dict(self):
        return {
            "pm25": round(self.pm25, 1),
            "haze": self.haze,
            "confidence": round(self.confidence, 1),
            "category": self.category,
        }


# ---------------------------------------------------------------------------
# โมเดล
# ---------------------------------------------------------------------------
class PM25Model:
    def __init__(self, model=None):
        self.model = model

    # ---- Training ----
    def train(self, X: np.ndarray, y: np.ndarray, test_size: float = 0.2):
        """
        เทรนโมเดลจากฟีเจอร์ X และค่า PM2.5 จริง y
        คืน dict สรุปผลการประเมิน (MAE บนชุดทดสอบ)
        """
        if joblib is None:
            raise RuntimeError("ต้องติดตั้ง scikit-learn และ joblib เพื่อเทรนโมเดล")

        if len(X) < 10:
            raise ValueError("ข้อมูลน้อยเกินไปสำหรับการเทรน (ต้องมีอย่างน้อย ~10 ตัวอย่าง)")

        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=test_size, random_state=42
        )
        model = GradientBoostingRegressor(
            n_estimators=300, max_depth=3, learning_rate=0.05, random_state=42
        )
        model.fit(X_train, y_train)
        self.model = model

        y_pred = model.predict(X_test)
        mae = float(mean_absolute_error(y_test, y_pred))
        return {
            "mae": mae,
            "n_train": len(X_train),
            "n_test": len(X_test),
        }

    # ---- Inference ----
    def predict(self, features: np.ndarray) -> Prediction:
        if self.model is None:
            raise RuntimeError("ยังไม่มีโมเดล — โปรดเทรนหรือโหลดโมเดลก่อน")
        x = features.reshape(1, -1)
        pm25 = float(self.model.predict(x)[0])
        pm25 = max(0.0, pm25)  # ค่าฝุ่นติดลบไม่ได้

        confidence = self._estimate_confidence(x, pm25)
        return Prediction(
            pm25=pm25,
            haze=haze_level(pm25),
            confidence=confidence,
            category=air_quality_category(pm25),
        )

    def _estimate_confidence(self, x: np.ndarray, pm25: float) -> float:
        """
        ประเมินความเชื่อมั่นจากการกระจายของ prediction ของต้นไม้แต่ละต้น
        (ยิ่งต้นไม้ทำนายใกล้กัน = เชื่อมั่นสูง)
        """
        try:
            # ค่าทำนายสะสมของแต่ละ stage
            staged = np.array(list(self.model.staged_predict(x))).ravel()
            spread = float(np.std(staged[-50:]))  # ความผันผวนช่วงท้าย
        except Exception:
            spread = 5.0
        # แปลง spread (µg/m³) เป็น % ความเชื่อมั่น
        conf = 100.0 * np.exp(-spread / 10.0)
        return float(np.clip(conf, 50.0, 99.0))

    # ---- Persistence ----
    def save(self, path: str):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        joblib.dump(self.model, path)

    @classmethod
    def load(cls, path: str) -> "PM25Model":
        if not os.path.exists(path):
            raise FileNotFoundError(f"ไม่พบไฟล์โมเดล: {path}")
        return cls(model=joblib.load(path))

    @classmethod
    def exists(cls, path: str) -> bool:
        return os.path.exists(path)

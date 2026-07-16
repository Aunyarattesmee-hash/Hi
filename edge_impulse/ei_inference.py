"""
รันโมเดลที่เทรนจาก Edge Impulse บน Raspberry Pi 5 (Edge Impulse for Linux)

หลังจากเทรนใน Edge Impulse Studio แล้วให้ Export เป็น "Linux (AARCH64)" .eim
    edge-impulse-linux-runner --download pm25-model.eim
หรือดาวน์โหลดจากเมนู Deployment แล้ววางไฟล์ .eim ไว้ที่ device/data/

โมดูลนี้ห่อ Edge Impulse SDK ให้มีอินเทอร์เฟซเหมือน device/model.py
(คืน pm25 / haze / confidence / category) เพื่อให้ collector.py เรียกใช้แทนได้

ต้องติดตั้ง:  pip install edge_impulse_linux
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "device"))
from model import Prediction, haze_level, air_quality_category  # noqa: E402

try:
    import cv2
    from edge_impulse_linux.image import ImageImpulseRunner
except ImportError:
    ImageImpulseRunner = None
    cv2 = None


# ---------------------------------------------------------------------------
# จับคู่ชื่อกลุ่ม (label) จาก Edge Impulse -> ค่า PM2.5 โดยประมาณ (µg/m³)
# แก้ตัวเลขตรงนี้ได้ตามต้องการ (คีย์ต้องเป็นตัวพิมพ์เล็กทั้งหมด)
#   no smog        = ไม่มีฝุ่นควัน เห็นภูเขา ฟ้าแจ่มใส  -> ฝุ่นน้อย
#   the smog clear = ควันน้อย เห็นภูเขาบางๆ            -> ฝุ่นปานกลาง
#   thick smog     = ควันเยอะ ไม่เห็นภูเขา             -> ฝุ่นมาก
# ---------------------------------------------------------------------------
LABEL_PM25 = {
    "no smog": 12.0,
    "the smog clear": 35.0,
    "thick smog": 90.0,
    "background": 12.0,     # ไม่พบวัตถุ = ถือว่าฟ้าใส
}
DEFAULT_PM25 = 12.0


def label_to_pm25(label) -> float:
    """แปลงชื่อกลุ่มเป็นค่า PM2.5 (รองรับทั้งชื่อข้อความและชื่อที่เป็นตัวเลข)"""
    if label is None:
        return DEFAULT_PM25
    key = str(label).strip().lower()
    if key in LABEL_PM25:
        return LABEL_PM25[key]
    try:
        return max(0.0, float(key))     # เผื่อกรณีตั้งชื่อกลุ่มเป็นตัวเลข
    except ValueError:
        return DEFAULT_PM25


def dominant_label(result: dict):
    """
    หากลุ่มที่ 'เด่นที่สุด' จากผลของ Edge Impulse
    รองรับ 3 แบบ: Object Detection (FOMO), Classification, Regression
    คืน (label, confidence[0-1], is_regression, regression_value)
    """
    # 1) Object Detection (FOMO) -> รวมความมั่นใจของแต่ละกล่องตามกลุ่ม
    boxes = result.get("bounding_boxes")
    if boxes:
        scores = {}
        for b in boxes:
            lbl = b.get("label")
            scores[lbl] = scores.get(lbl, 0.0) + float(b.get("value", 0.0))
        best = max(scores, key=scores.get)
        conf = max(float(b.get("value", 0.0)) for b in boxes if b.get("label") == best)
        return best, conf, False, None

    # 2) Classification -> เอากลุ่มที่ความน่าจะเป็นสูงสุด
    classes = result.get("classification")
    if classes:
        best = max(classes, key=classes.get)
        return best, float(classes[best]), False, None

    # 3) Regression -> ได้ค่าตัวเลขตรง ๆ
    if "regression" in result:
        return None, 0.9, True, float(result["regression"]["value"])

    return None, 0.0, False, None


class EdgeImpulsePM25:
    """โหลดและรันโมเดล .eim ของ Edge Impulse (regression: ทำนายค่า PM2.5)"""

    def __init__(self, model_path: str):
        if ImageImpulseRunner is None:
            raise RuntimeError(
                "ต้องติดตั้ง edge_impulse_linux และ opencv-python ก่อน\n"
                "  pip install edge_impulse_linux opencv-python"
            )
        if not os.path.exists(model_path):
            raise FileNotFoundError(f"ไม่พบไฟล์โมเดล .eim: {model_path}")
        self.model_path = model_path
        self.runner = ImageImpulseRunner(model_path)
        self.model_info = self.runner.init()
        print("โหลดโมเดล Edge Impulse:",
              self.model_info["project"]["name"],
              "v" + str(self.model_info["project"]["deploy_version"]))

    def predict(self, frame) -> Prediction:
        """รับภาพ BGR (numpy) คืนผลการประเมินแบบเดียวกับ device/model.py"""
        # Edge Impulse ต้องการ RGB
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        features, _ = self.runner.get_features_from_image(rgb)
        res = self.runner.classify(features)
        result = res["result"]

        # รองรับทั้ง FOMO (Object Detection), Classification และ Regression
        label, conf, is_regression, reg_value = dominant_label(result)
        if is_regression:
            pm25 = max(0.0, reg_value)
            confidence = 90.0
        else:
            # แปลงชื่อกลุ่ม (no smog / the smog clear / thick smog) -> ค่า PM2.5
            pm25 = label_to_pm25(label)
            confidence = round(conf * 100.0, 1)

        return Prediction(
            pm25=pm25,
            haze=haze_level(pm25),
            confidence=confidence,
            category=air_quality_category(pm25),
        )

    def close(self):
        if self.runner:
            self.runner.stop()


if __name__ == "__main__":
    import config  # noqa: E402
    model_file = os.path.join(config.DATA_DIR, "pm25-model.eim")
    ei = EdgeImpulsePM25(model_file)
    img = cv2.imread(sys.argv[1]) if len(sys.argv) > 1 else None
    if img is not None:
        print(ei.predict(img).as_dict())
    ei.close()

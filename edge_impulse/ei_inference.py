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
        # Regression -> ค่าจะอยู่ใน result["regression"]["value"]
        # Classification -> เอาคลาสที่มีความน่าจะเป็นสูงสุด (fallback)
        if "regression" in result:
            pm25 = float(result["regression"]["value"])
            confidence = 90.0
        else:
            classes = result.get("classification", {})
            # กรณีตั้งเป็น classification ให้ตีความชื่อคลาสเป็นตัวเลข
            best = max(classes, key=classes.get) if classes else "0"
            try:
                pm25 = float(best)
            except ValueError:
                pm25 = 0.0
            confidence = float(classes.get(best, 0.0)) * 100.0

        pm25 = max(0.0, pm25)
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

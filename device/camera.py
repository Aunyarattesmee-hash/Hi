"""
ถ่ายภาพท้องฟ้าจากกล้อง Logitech C270 (USB Webcam) ด้วย OpenCV

C270 เป็นกล้อง USB ธรรมดา จึงเปิดผ่าน cv2.VideoCapture(index) ได้เลย
โดยทั่วไปจะเป็น /dev/video0 (index 0)
"""
from __future__ import annotations

import os
import time
from datetime import datetime

try:
    import cv2
except ImportError:
    cv2 = None

import config


class SkyCamera:
    def __init__(self, index: int = 0, width: int = 1280, height: int = 720):
        if cv2 is None:
            raise RuntimeError("ไม่พบไลบรารี opencv-python — ติดตั้งด้วย: pip install opencv-python")
        self.index = index
        self.width = width
        self.height = height

    def capture(self, save_path: str | None = None):
        """
        ถ่ายภาพ 1 รูป คืนค่า (ndarray ภาพ BGR, path ที่บันทึก)
        ถ้าไม่ระบุ save_path จะตั้งชื่อไฟล์ตาม timestamp ใน IMAGE_DIR
        """
        cap = cv2.VideoCapture(self.index)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        if not cap.isOpened():
            raise IOError(f"เปิดกล้อง index={self.index} ไม่สำเร็จ")

        # อ่านทิ้งไม่กี่เฟรมแรกเพื่อให้ auto-exposure ปรับตัว
        frame = None
        for _ in range(5):
            ok, frame = cap.read()
            time.sleep(0.1)
        cap.release()

        if frame is None:
            raise IOError("อ่านภาพจากกล้องไม่สำเร็จ")

        if save_path is None:
            config.ensure_dirs()
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            save_path = os.path.join(config.IMAGE_DIR, f"sky_{ts}.jpg")

        cv2.imwrite(save_path, frame)
        return frame, save_path

    @staticmethod
    def crop_sky(frame,
                 top_ratio: float = config.SKY_CROP_TOP_RATIO,
                 bottom_ratio: float = config.SKY_CROP_BOTTOM_RATIO):
        """
        ตัดเอาเฉพาะส่วนท้องฟ้า (ครึ่งบนของภาพ) เพื่อลด noise จากพื้น/อาคาร
        top_ratio, bottom_ratio = สัดส่วนความสูงที่ต้องการเก็บ
        """
        h = frame.shape[0]
        y0 = int(h * top_ratio)
        y1 = int(h * bottom_ratio)
        return frame[y0:y1, :]


if __name__ == "__main__":
    cam = SkyCamera(config.CAMERA_INDEX, config.CAMERA_WIDTH, config.CAMERA_HEIGHT)
    _, path = cam.capture()
    print("บันทึกภาพที่:", path)

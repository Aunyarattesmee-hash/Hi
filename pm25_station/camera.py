# -*- coding: utf-8 -*-
"""
camera.py — ถ่ายภาพท้องฟ้าจากกล้อง webcam (Logitech C270) ด้วย OpenCV

ติดตั้งไลบรารีก่อนใช้:
    pip install opencv-python
"""

import os
import time


class SkyCamera:
    """ถ่ายภาพจาก webcam แล้วบันทึกเป็นไฟล์ .jpg"""

    def __init__(self, index=0, width=1280, height=720, save_dir="images"):
        self.index = index
        self.width = width
        self.height = height
        self.save_dir = save_dir
        os.makedirs(self.save_dir, exist_ok=True)

    def capture(self):
        """ถ่าย 1 ภาพ คืน path ของไฟล์ที่บันทึก"""
        import cv2

        cam = cv2.VideoCapture(self.index)
        cam.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
        cam.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
        # อ่านทิ้งไปสองสามเฟรมให้กล้องปรับแสงก่อน
        for _ in range(3):
            cam.read()
        ok, frame = cam.read()
        cam.release()
        if not ok:
            raise IOError("ถ่ายภาพไม่สำเร็จ (เช็คว่ากล้องเสียบอยู่ที่ /dev/video0)")

        filename = time.strftime("sky_%Y%m%d_%H%M%S.jpg")
        path = os.path.join(self.save_dir, filename)
        cv2.imwrite(path, frame)
        return path


# ---- ทดสอบไฟล์นี้เดี่ยว ๆ ----
if __name__ == "__main__":
    cam = SkyCamera()
    print("บันทึกภาพไว้ที่:", cam.capture())

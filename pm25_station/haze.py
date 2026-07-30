# -*- coding: utf-8 -*-
"""
haze.py — ดูภาพท้องฟ้าแล้วบอก "ระดับฝุ่นควัน" (ไม่บอกเป็นตัวเลข)

หลักการ:
  ท้องฟ้าใส  -> สีน้ำเงิน "อิ่มสี" (saturation สูง)          -> ไม่มีฝุ่นควัน
  มีควันมาก  -> สีฟ้าจางลง กลายเป็นขาว/เทา (saturation ต่ำ) -> ฝุ่นควันหนักมาก

เราจึงวัด "ความอิ่มสี (Saturation)" เฉลี่ยของท้องฟ้าในภาพ
ค่ายิ่งต่ำ = ฟ้ายิ่งขุ่น = ควันยิ่งเยอะ

ระดับที่คืนกลับมามี 3 ระดับ:
  🟢 ไม่มีฝุ่นควัน
  🟡 มีฝุ่นควันปานกลาง
  🔴 ฝุ่นควันหนักมาก

* เกณฑ์ตัดระดับ (SAT_CLEAR / SAT_MODERATE) ปรับได้ตามหน้างานจริง
  ถ้ารู้สึกว่ามันบอก "หนักมาก" ง่ายไป ให้ลดตัวเลขลง
"""

# เกณฑ์ความอิ่มสี (0-255) — ปรับได้
SAT_CLEAR = 90       # อิ่มสี >= ค่านี้ = ฟ้าใส -> ไม่มีฝุ่นควัน
SAT_MODERATE = 45    # อิ่มสีอยู่ระหว่าง 45-90 = ปานกลาง, ต่ำกว่า 45 = หนักมาก

# ชื่อระดับ + อีโมจิ (เอาไว้โชว์บนเว็บ)
LEVEL_NONE = "ไม่มีฝุ่นควัน"
LEVEL_MODERATE = "มีฝุ่นควันปานกลาง"
LEVEL_HEAVY = "ฝุ่นควันหนักมาก"


def level_from_saturation(sat):
    """แปลงค่าความอิ่มสีเฉลี่ย -> ชื่อระดับ"""
    if sat >= SAT_CLEAR:
        return LEVEL_NONE
    elif sat >= SAT_MODERATE:
        return LEVEL_MODERATE
    else:
        return LEVEL_HEAVY


def classify_image(image_path):
    """
    รับ path ของไฟล์ภาพ -> คืน dict เช่น
        {"level": "มีฝุ่นควันปานกลาง", "saturation": 63.2}
    """
    import cv2
    import numpy as np

    img = cv2.imread(image_path)
    if img is None:
        raise IOError("เปิดไฟล์ภาพไม่ได้: %s" % image_path)

    # เอาเฉพาะครึ่งบนของภาพ (ส่วนที่เป็นท้องฟ้า) มาวิเคราะห์
    h = img.shape[0]
    sky = img[: h // 2, :, :]

    # แปลงเป็นระบบสี HSV แล้วดูช่อง S (Saturation = ความอิ่มสี)
    hsv = cv2.cvtColor(sky, cv2.COLOR_BGR2HSV)
    sat = float(np.mean(hsv[:, :, 1]))

    return {"level": level_from_saturation(sat), "saturation": round(sat, 1)}


# ---- ทดสอบไฟล์นี้เดี่ยว ๆ: ใส่ชื่อไฟล์ภาพแล้วกด Run ----
if __name__ == "__main__":
    result = classify_image("images/test.jpg")
    print("ระดับฝุ่นควันจากภาพ:", result["level"], "(อิ่มสี =", result["saturation"], ")")

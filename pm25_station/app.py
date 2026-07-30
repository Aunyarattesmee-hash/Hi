# -*- coding: utf-8 -*-
"""
app.py — เว็บเซิร์ฟเวอร์ (Dashboard) + ตัวเก็บข้อมูลในตัวเดียว

รันไฟล์นี้ไฟล์เดียว (กด Run ใน Thonny) จะได้ทั้ง:
  1. ตัวอ่านเซนเซอร์วนอยู่เบื้องหลัง (เก็บลง pm25.db)
  2. หน้าเว็บ Dashboard ให้เปิดดูผลผ่านเบราว์เซอร์

พอรันแล้ว เปิดเบราว์เซอร์บน Pi ไปที่:   http://localhost:8000
หรือดูจากมือถือ/คอมเครื่องอื่นในวง Wi-Fi เดียวกัน:  http://<ไอพีของ Pi>:8000
(หาไอพีของ Pi ได้จากคำสั่ง hostname -I)

ต้องติดตั้ง Flask ก่อน:  pip install flask
"""

import threading

from flask import Flask, jsonify, send_from_directory

import config
from database import Database
from collector import collect_forever

app = Flask(__name__, static_folder="web", static_url_path="")
db = Database(config.DB_FILE)


# ---- หน้าเว็บหลัก ----
@app.route("/")
def index():
    return send_from_directory("web", "index.html")


# ---- ช่องข้อมูล (API) ที่หน้าเว็บมาขอ ----
@app.route("/api/latest")
def api_latest():
    """ค่าล่าสุด 1 ชุด"""
    return jsonify(db.latest() or {})


@app.route("/api/history")
def api_history():
    """ข้อมูลย้อนหลังไว้วาดกราฟ"""
    return jsonify(db.history(limit=200))


# ---- เปิดดูภาพที่กล้องถ่ายไว้ ----
@app.route("/images/<name>")
def images(name):
    return send_from_directory("images", name)


def main():
    # เปิด thread เบื้องหลังให้คอยอ่านเซนเซอร์เก็บลงฐานข้อมูล
    worker = threading.Thread(target=collect_forever, args=(db,), daemon=True)
    worker.start()

    print("เปิดเว็บที่ http://localhost:%d  (กด Stop สีแดงเพื่อหยุด)" % config.WEB_PORT)
    # use_reloader=False กันไม่ให้ thread อ่านเซนเซอร์ถูกเปิดซ้ำ 2 รอบ
    app.run(host=config.WEB_HOST, port=config.WEB_PORT, use_reloader=False)


if __name__ == "__main__":
    main()

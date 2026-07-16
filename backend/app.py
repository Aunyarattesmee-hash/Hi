"""
Backend (หลังบ้าน) ของระบบติดตามและประเมินค่าฝุ่น PM2.5 ด้วย AI
Framework: Flask + SQLite

หน้าที่:
  - รับข้อมูล/ภาพจาก Raspberry Pi   (POST /api/readings)
  - ให้ข้อมูลแก่ Dashboard (หน้าบ้าน) ผ่าน REST API
  - เสิร์ฟหน้าเว็บและรูปภาพ

รันด้วย:  python app.py   (dev)
โปรดักชัน:  gunicorn -w 2 -b 0.0.0.0:8000 app:app
"""
from __future__ import annotations

import csv
import io
import os
from datetime import datetime
from werkzeug.utils import secure_filename

from flask import (Flask, jsonify, request, send_from_directory,
                   send_file, abort, Response)

import database

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")
UPLOAD_DIR = os.path.join(BASE_DIR, "data", "images")

# กุญแจ API ให้ตรงกับฝั่ง Pi (config.BACKEND_API_KEY)
API_KEY = os.getenv("BACKEND_API_KEY", "changeme-secret-key")
STATION_NAME = os.getenv("STATION_NAME", "โรงเรียนปายวิทยาคาร อ.ปาย จ.แม่ฮ่องสอน")

app = Flask(__name__, static_folder=None)


# ---------------------------------------------------------------------------
# เริ่มต้นระบบ
# ---------------------------------------------------------------------------
os.makedirs(UPLOAD_DIR, exist_ok=True)
database.init_db()


def require_api_key():
    key = request.headers.get("X-API-Key", "")
    if key != API_KEY:
        abort(401, description="API key ไม่ถูกต้อง")


# ---------------------------------------------------------------------------
# รับข้อมูลจาก Raspberry Pi
# ---------------------------------------------------------------------------
@app.post("/api/readings")
def ingest_reading():
    require_api_key()

    form = request.form
    image_filename = None
    if "image" in request.files:
        f = request.files["image"]
        if f and f.filename:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            image_filename = f"{ts}_{secure_filename(f.filename)}"
            f.save(os.path.join(UPLOAD_DIR, image_filename))

    def num(key, default=None):
        val = form.get(key)
        if val is None or val == "":
            return default
        try:
            return float(val)
        except ValueError:
            return default

    data = {
        "timestamp": form.get("timestamp") or datetime.now().isoformat(timespec="seconds"),
        "station_id": form.get("station_id"),
        "pm2_5": num("pm2_5", 0.0),
        "pm2_5_sensor": num("pm2_5_sensor"),
        "temperature": num("temperature"),
        "humidity": num("humidity"),
        "haze": form.get("haze"),
        "confidence": num("confidence"),
        "quality_label": form.get("quality_label"),
        "quality_level": form.get("quality_level"),
        "source": form.get("source", "sensor"),
        "image_filename": image_filename,
    }
    new_id = database.insert_reading(data)
    return jsonify({"status": "ok", "id": new_id}), 201


# ---------------------------------------------------------------------------
# API สำหรับ Dashboard
# ---------------------------------------------------------------------------
@app.get("/api/latest")
def api_latest():
    row = database.get_latest()
    if not row:
        return jsonify({"available": False, "station_name": STATION_NAME})
    row["available"] = True
    row["station_name"] = STATION_NAME
    row["daily_avg"] = database.get_daily_average(1)
    row["weekly_avg"] = database.get_daily_average(7)
    return jsonify(row)


@app.get("/api/history")
def api_history():
    limit = request.args.get("limit", default=10, type=int)
    limit = max(1, min(limit, 200))
    return jsonify(database.get_history(limit))


@app.get("/api/trend")
def api_trend():
    range_key = request.args.get("range", default="today")
    if range_key not in ("today", "7d", "30d"):
        range_key = "today"
    return jsonify(database.get_trend(range_key))


@app.get("/api/export.csv")
def api_export():
    def generate():
        buf = io.StringIO()
        writer = csv.writer(buf)
        header = ["id", "timestamp", "station_id", "pm2_5", "pm2_5_sensor",
                  "temperature", "humidity", "haze", "confidence",
                  "quality_label", "quality_level", "source", "image_filename"]
        writer.writerow(header)
        yield buf.getvalue()
        buf.seek(0); buf.truncate(0)
        for row in database.iter_all_rows():
            writer.writerow([row.get(k) for k in header])
            yield buf.getvalue()
            buf.seek(0); buf.truncate(0)

    filename = f"pm25_export_{datetime.now().strftime('%Y%m%d')}.csv"
    return Response(
        generate(),
        mimetype="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# เสิร์ฟรูปภาพ
# ---------------------------------------------------------------------------
@app.get("/api/image/<path:filename>")
def api_image(filename):
    return send_from_directory(UPLOAD_DIR, filename)


@app.get("/api/latest-image")
def api_latest_image():
    row = database.get_latest()
    if row and row.get("image_filename"):
        path = os.path.join(UPLOAD_DIR, row["image_filename"])
        if os.path.exists(path):
            return send_file(path)
    # ไม่มีรูป -> ส่ง placeholder
    ph = os.path.join(FRONTEND_DIR, "assets", "no-image.svg")
    if os.path.exists(ph):
        return send_file(ph)
    abort(404)


# ---------------------------------------------------------------------------
# เสิร์ฟหน้าเว็บ (Frontend)
# ---------------------------------------------------------------------------
@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def static_files(path):
    full = os.path.join(FRONTEND_DIR, path)
    if os.path.exists(full) and os.path.isfile(full):
        return send_from_directory(FRONTEND_DIR, path)
    # SPA fallback
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    port = int(os.getenv("PORT", "8000"))
    debug = os.getenv("FLASK_DEBUG", "0") == "1"
    app.run(host="0.0.0.0", port=port, debug=debug)

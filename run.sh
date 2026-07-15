#!/usr/bin/env bash
# ============================================================
#  run.sh — รันทั้งระบบด้วยไฟล์เดียว
#
#  ครั้งแรกจะ: สร้าง virtualenv + ติดตั้งไลบรารีให้อัตโนมัติ
#  ทุกครั้งจะ: เปิด Backend (เว็บ) + รันตัวเก็บข้อมูล
#
#  วิธีใช้:
#     ./run.sh              # ใช้เซนเซอร์จริง (ต่ออุปกรณ์แล้ว)
#     ./run.sh --simulate   # โหมดจำลอง (ยังไม่ต้องต่อเซนเซอร์)
#     ./run.sh --simulate --once   # จำลองรอบเดียวแล้วหยุด
#
#  กด Ctrl+C เพื่อหยุดทั้งหมด
# ============================================================
set -u

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# ---- อ่าน argument ----
SIM=""
ONCE=""
for a in "$@"; do
  case "$a" in
    --simulate) SIM="--simulate" ;;
    --once)     ONCE="--once" ;;
    *) echo "ไม่รู้จักตัวเลือก: $a"; exit 1 ;;
  esac
done

# ---- ตั้งค่า (แก้ได้ หรือ export มาก่อนเรียกสคริปต์) ----
export BACKEND_API_KEY="${BACKEND_API_KEY:-mysecret}"
export PORT="${PORT:-8000}"
export BACKEND_URL="${BACKEND_URL:-http://localhost:${PORT}}"

# ---- 1) virtualenv ----
if [ ! -d ".venv" ]; then
  echo "==> สร้าง virtualenv ครั้งแรก..."
  python3 -m venv .venv
fi
# shellcheck disable=SC1091
source .venv/bin/activate

# ---- 2) ติดตั้งไลบรารี (เฉพาะครั้งแรก) ----
if [ ! -f ".venv/.installed" ]; then
  echo "==> ติดตั้งไลบรารี (ครั้งแรกอาจใช้เวลา 3-5 นาที)..."
  pip install --upgrade pip -q
  pip install -q -r backend/requirements.txt -r device/requirements.txt
  touch .venv/.installed
  echo "==> ติดตั้งเสร็จแล้ว"
fi

# ---- 3) เปิด Backend เบื้องหลัง ----
echo "==> เริ่ม Backend (เว็บเซิร์ฟเวอร์)..."
( cd backend && python app.py > "$SCRIPT_DIR/backend.log" 2>&1 ) &
BACKEND_PID=$!

# ปิด Backend เมื่อสคริปต์จบ/กด Ctrl+C
cleanup() {
  echo ""
  echo "==> กำลังหยุดระบบ..."
  kill "$BACKEND_PID" 2>/dev/null
  wait "$BACKEND_PID" 2>/dev/null
  echo "==> หยุดเรียบร้อย"
  exit 0
}
trap cleanup INT TERM

# รอ Backend พร้อม
sleep 4
if ! kill -0 "$BACKEND_PID" 2>/dev/null; then
  echo "❌ Backend เปิดไม่สำเร็จ — ดูรายละเอียดใน backend.log"
  tail -n 20 "$SCRIPT_DIR/backend.log"
  exit 1
fi

IP="$(hostname -I 2>/dev/null | awk '{print $1}')"
[ -z "$IP" ] && IP="localhost"
echo "======================================================"
echo "  ✅ ระบบทำงานแล้ว"
echo "     เปิด Dashboard ที่:  http://${IP}:${PORT}"
[ -n "$SIM" ] && echo "     โหมด: จำลอง (--simulate)" || echo "     โหมด: เซนเซอร์จริง"
echo "     กด Ctrl+C เพื่อหยุดทั้งหมด"
echo "======================================================"

# ---- 4) รันตัวเก็บข้อมูล (โฟร์กราวด์) ----
cd device
python collector.py $ONCE $SIM

# ถ้า collector จบเอง (เช่น --once) ให้ปิด backend ด้วย
cleanup

// app.js — ทำให้หน้าเว็บมีชีวิต: ดึงข้อมูลจากเซิร์ฟเวอร์มาแสดง + วาดกราฟ

// แปลงค่า PM2.5 -> ป้ายคุณภาพอากาศ (ข้อความ + คลาสสีตามมาตรฐานไทย)
function airQuality(pm) {
  if (pm <= 25)  return { text: "ดีมาก",            cls: "lv-good"   };
  if (pm <= 37.5) return { text: "ดี",              cls: "lv-ok"     };
  if (pm <= 75)  return { text: "ปานกลาง",          cls: "lv-medium" };
  if (pm <= 115) return { text: "เริ่มมีผลต่อสุขภาพ", cls: "lv-bad"    };
  return             { text: "มีผลต่อสุขภาพ",       cls: "lv-danger" };
}

// เลือกสีของป้าย "ระดับฝุ่นควันจากภาพ"
function hazeClass(level) {
  if (level === "ไม่มีฝุ่นควัน")     return "lv-good";
  if (level === "มีฝุ่นควันปานกลาง") return "lv-medium";
  if (level === "ฝุ่นควันหนักมาก")   return "lv-danger";
  return "";
}

// ดึงค่าล่าสุดมาแสดงบนการ์ด
async function loadLatest() {
  const res = await fetch("/api/latest");
  const d = await res.json();
  if (!d || d.pm2_5 === undefined) return;

  document.getElementById("pm25").textContent = d.pm2_5.toFixed(1);
  document.getElementById("temp").textContent = d.temperature.toFixed(1);
  document.getElementById("humidity").textContent = d.humidity.toFixed(0);

  const q = airQuality(d.pm2_5);
  const badge = document.getElementById("quality");
  badge.textContent = q.text;
  badge.className = "badge " + q.cls;

  const hz = document.getElementById("haze");
  hz.textContent = d.haze || "-";
  hz.className = "haze-badge " + hazeClass(d.haze);

  // ภาพจากกล้อง (ถ้ามี)
  const photo = document.getElementById("photo");
  const noPhoto = document.getElementById("no-photo");
  if (d.image) {
    photo.src = "/images/" + d.image + "?t=" + Date.now();
    photo.style.display = "block";
    noPhoto.style.display = "none";
  } else {
    photo.style.display = "none";
    noPhoto.style.display = "block";
  }

  // เวลาอัปเดตล่าสุด
  const t = new Date(d.ts * 1000);
  document.getElementById("updated").textContent =
    "อัปเดตล่าสุด: " + t.toLocaleTimeString("th-TH");
}

// วาดกราฟเส้น PM2.5 ด้วย canvas ธรรมดา (ไม่ต้องพึ่งไลบรารีภายนอก)
async function loadChart() {
  const res = await fetch("/api/history");
  const rows = await res.json();
  if (!rows.length) return;

  const canvas = document.getElementById("chart");
  const ctx = canvas.getContext("2d");
  const W = canvas.width, H = canvas.height, pad = 30;
  ctx.clearRect(0, 0, W, H);

  const values = rows.map(r => r.pm2_5);
  const maxV = Math.max(50, ...values) * 1.1;

  // เส้นแกนล่าง
  ctx.strokeStyle = "#334155";
  ctx.beginPath();
  ctx.moveTo(pad, H - pad); ctx.lineTo(W - pad, H - pad); ctx.stroke();

  // เส้นกราฟ
  ctx.strokeStyle = "#38bdf8";
  ctx.lineWidth = 2;
  ctx.beginPath();
  values.forEach((v, i) => {
    const x = pad + (W - 2 * pad) * (i / Math.max(1, values.length - 1));
    const y = (H - pad) - (H - 2 * pad) * (v / maxV);
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  });
  ctx.stroke();

  // จุดสุดท้าย + ตัวเลข
  const last = values[values.length - 1];
  ctx.fillStyle = "#e2e8f0";
  ctx.font = "14px sans-serif";
  ctx.fillText(last.toFixed(1) + " µg/m³", W - pad - 90, pad);
}

function refresh() { loadLatest(); loadChart(); }

refresh();
setInterval(refresh, 5000);   // อัปเดตทุก 5 วินาที

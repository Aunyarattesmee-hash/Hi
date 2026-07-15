/* ============================================================
   Dashboard logic — ระบบติดตามและประเมินค่าฝุ่น PM2.5
   ไม่พึ่งไลบรารีภายนอก (วาดกราฟด้วย Canvas เอง) เพื่อให้ทำงานแบบ offline บน Pi ได้
   ============================================================ */
'use strict';

const AQ_BANDS = [
  { max: 15,    color: '#2e7d32', label: 'ดีมาก' },
  { max: 25,    color: '#9ccc65', label: 'ดี' },
  { max: 37.5,  color: '#ffb300', label: 'ปานกลาง' },
  { max: 75,    color: '#fb8c00', label: 'เริ่มมีผลต่อสุขภาพ' },
  { max: 1e9,   color: '#e53935', label: 'มีผลกระทบต่อสุขภาพ' },
];

function bandFor(pm) { return AQ_BANDS.find(b => pm <= b.max) || AQ_BANDS[AQ_BANDS.length - 1]; }

let settings = JSON.parse(localStorage.getItem('pm25_settings') || '{}');
let refreshTimer = null;
let currentRange = 'today';

/* ---------------------- Helpers ---------------------- */
async function getJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error('HTTP ' + r.status);
  return r.json();
}
function fmt(v, d = 1) { return (v === null || v === undefined) ? '—' : Number(v).toFixed(d); }
function fmtDate(iso) {
  if (!iso) return '—';
  const dt = new Date(iso.replace(' ', 'T'));
  if (isNaN(dt)) return iso;
  return dt.toLocaleString('th-TH', { day: '2-digit', month: '2-digit', year: 'numeric',
    hour: '2-digit', minute: '2-digit', second: '2-digit' });
}
function timeOnly(iso) {
  if (!iso) return '—';
  const dt = new Date(iso.replace(' ', 'T'));
  return isNaN(dt) ? iso : dt.toLocaleTimeString('th-TH', { hour12: false });
}

/* ---------------------- Clock ---------------------- */
function tickClock() {
  const now = new Date();
  document.getElementById('headerDate').textContent =
    '📅 ' + now.toLocaleDateString('th-TH', { day: 'numeric', month: 'long', year: 'numeric' });
  document.getElementById('headerTime').textContent =
    '🕒 ' + now.toLocaleTimeString('th-TH', { hour12: false });
}

/* ---------------------- Latest (cards) ---------------------- */
async function loadLatest() {
  let data;
  try { data = await getJSON('/api/latest'); }
  catch (e) { console.error(e); return; }

  document.getElementById('stationName').textContent = data.station_name || '—';
  document.getElementById('settingsStation').textContent = data.station_name || '—';

  if (!data.available) {
    document.getElementById('pmValue').textContent = '—';
    document.getElementById('pmQuality').textContent = 'ยังไม่มีข้อมูล';
    document.getElementById('historyBody').innerHTML =
      '<tr><td colspan="5" class="empty">ยังไม่มีข้อมูล — เริ่มเก็บด้วย collector.py</td></tr>';
    return;
  }

  const pm = data.pm2_5;
  const band = bandFor(pm);
  document.getElementById('pmValue').textContent = fmt(pm, 1);
  document.getElementById('pmValue').style.color = band.color;
  document.getElementById('pmQuality').textContent = data.quality_label || band.label;
  const badge = document.getElementById('pmBadge');
  badge.textContent = data.haze || band.label;
  badge.style.background = band.color;
  badge.style.color = '#fff';

  // ตำแหน่ง marker บนแถบสี (map 0-150 -> 0-100%)
  const pct = Math.max(0, Math.min(100, (pm / 150) * 100));
  document.getElementById('pmMarker').style.left = pct + '%';
  document.getElementById('pmUpdated').textContent = timeOnly(data.timestamp);

  document.getElementById('tempValue').textContent = fmt(data.temperature, 1);
  document.getElementById('humValue').textContent = fmt(data.humidity, 0);

  // webcam
  const img = document.getElementById('webcamImg');
  img.src = '/api/latest-image?t=' + Date.now();
  document.getElementById('webcamTs').textContent = fmtDate(data.timestamp);
}

/* ---------------------- History ---------------------- */
async function loadHistory() {
  let rows;
  try { rows = await getJSON('/api/history?limit=5'); }
  catch (e) { return; }
  const body = document.getElementById('historyBody');
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="5" class="empty">ยังไม่มีข้อมูล</td></tr>';
    return;
  }
  body.innerHTML = rows.map(r => {
    const band = bandFor(r.pm2_5);
    const imgCell = r.image_filename
      ? `<img src="/api/image/${r.image_filename}" alt="">` : '—';
    return `<tr>
      <td>${fmtDate(r.timestamp)}</td>
      <td><span class="pm-chip" style="background:${band.color}">${fmt(r.pm2_5, 1)}</span></td>
      <td>${fmt(r.temperature, 1)}</td>
      <td>${fmt(r.humidity, 0)}</td>
      <td>${imgCell}</td>
    </tr>`;
  }).join('');
}

async function loadHistoryFull() {
  const limit = document.getElementById('historyLimit').value;
  let rows;
  try { rows = await getJSON('/api/history?limit=' + limit); }
  catch (e) { return; }
  const body = document.getElementById('historyFullBody');
  if (!rows.length) {
    body.innerHTML = '<tr><td colspan="8" class="empty">ยังไม่มีข้อมูล</td></tr>';
    return;
  }
  body.innerHTML = rows.map(r => {
    const band = bandFor(r.pm2_5);
    const imgCell = r.image_filename
      ? `<img src="/api/image/${r.image_filename}" alt="">` : '—';
    return `<tr>
      <td>${fmtDate(r.timestamp)}</td>
      <td><span class="pm-chip" style="background:${band.color}">${fmt(r.pm2_5, 1)}</span></td>
      <td>${fmt(r.pm2_5_sensor, 1)}</td>
      <td>${fmt(r.temperature, 1)}</td>
      <td>${fmt(r.humidity, 0)}</td>
      <td>${r.haze || '—'}</td>
      <td>${r.confidence != null ? fmt(r.confidence, 0) + '%' : '—'}</td>
      <td>${imgCell}</td>
    </tr>`;
  }).join('');
}

/* ---------------------- Canvas line chart ---------------------- */
function drawLineChart(canvas, points, opts = {}) {
  const dpr = window.devicePixelRatio || 1;
  const cssW = canvas.clientWidth, cssH = canvas.clientHeight;
  canvas.width = cssW * dpr; canvas.height = cssH * dpr;
  const ctx = canvas.getContext('2d');
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssW, cssH);

  const padL = 42, padR = 14, padT = 14, padB = 34;
  const W = cssW - padL - padR, H = cssH - padT - padB;

  if (!points.length) {
    ctx.fillStyle = '#9ca3af'; ctx.font = '14px Sarabun, sans-serif';
    ctx.textAlign = 'center';
    ctx.fillText('ยังไม่มีข้อมูลสำหรับช่วงเวลานี้', cssW / 2, cssH / 2);
    return;
  }

  const ys = points.map(p => p.y);
  let yMax = Math.max(...ys, opts.suggestedMax || 0);
  let yMin = Math.min(...ys, 0);
  yMax = Math.ceil((yMax * 1.15) / 10) * 10 || 10;

  const xFor = i => padL + (points.length === 1 ? W / 2 : (i / (points.length - 1)) * W);
  const yFor = v => padT + H - ((v - yMin) / (yMax - yMin || 1)) * H;

  // แถบสีคุณภาพอากาศ (เฉพาะกราฟ PM2.5)
  if (opts.bands) {
    let prev = yMin;
    for (const b of AQ_BANDS) {
      const top = Math.min(b.max, yMax), bottom = prev;
      if (top <= bottom) { prev = b.max; continue; }
      ctx.fillStyle = b.color + '22';
      const y1 = yFor(top), y2 = yFor(bottom);
      ctx.fillRect(padL, y1, W, y2 - y1);
      prev = b.max;
      if (b.max >= yMax) break;
    }
  }

  // เส้นกริดแนวนอน + ป้ายแกน Y
  ctx.strokeStyle = '#e5e7eb'; ctx.fillStyle = '#9ca3af';
  ctx.font = '11px Sarabun, sans-serif'; ctx.textAlign = 'right';
  const steps = 5;
  for (let i = 0; i <= steps; i++) {
    const v = yMin + (i / steps) * (yMax - yMin);
    const y = yFor(v);
    ctx.beginPath(); ctx.moveTo(padL, y); ctx.lineTo(padL + W, y); ctx.stroke();
    ctx.fillText(Math.round(v), padL - 6, y + 3);
  }

  // ป้ายแกน X (เวลา) — แสดงบางจุด
  ctx.textAlign = 'center';
  const labelEvery = Math.ceil(points.length / 7);
  points.forEach((p, i) => {
    if (i % labelEvery === 0 || i === points.length - 1) {
      ctx.fillText(p.label, xFor(i), padT + H + 18);
    }
  });

  // พื้นที่ใต้เส้น (gradient)
  const grad = ctx.createLinearGradient(0, padT, 0, padT + H);
  grad.addColorStop(0, (opts.color || '#3b82f6') + '33');
  grad.addColorStop(1, (opts.color || '#3b82f6') + '02');
  ctx.beginPath();
  points.forEach((p, i) => { const x = xFor(i), y = yFor(p.y); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.lineTo(xFor(points.length - 1), padT + H);
  ctx.lineTo(xFor(0), padT + H);
  ctx.closePath(); ctx.fillStyle = grad; ctx.fill();

  // เส้นกราฟ
  ctx.beginPath();
  points.forEach((p, i) => { const x = xFor(i), y = yFor(p.y); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); });
  ctx.strokeStyle = opts.color || '#3b82f6'; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.stroke();

  // จุดข้อมูล
  ctx.fillStyle = opts.color || '#3b82f6';
  points.forEach((p, i) => {
    ctx.beginPath(); ctx.arc(xFor(i), yFor(p.y), 3, 0, Math.PI * 2); ctx.fill();
  });
}

const METRIC_META = {
  pm2_5:       { color: '#3b82f6', bands: true,  suggestedMax: 100 },
  temperature: { color: '#ef4444', bands: false, suggestedMax: 40 },
  humidity:    { color: '#8b5cf6', bands: false, suggestedMax: 100 },
};

async function loadTrend(range, canvasId, metric) {
  metric = metric || document.getElementById('metricSelect').value;
  let rows;
  try { rows = await getJSON('/api/trend?range=' + range); }
  catch (e) { return; }
  const points = rows.map(r => ({
    y: Number(r[metric]) || 0,
    label: timeOnly(r.timestamp).slice(0, 5),
  }));
  const meta = METRIC_META[metric] || METRIC_META.pm2_5;
  drawLineChart(document.getElementById(canvasId), points, meta);
  return rows;
}

async function loadTrendFull(range) {
  const rows = await loadTrend(range, 'trendChartFull', 'pm2_5');
  if (!rows) return;
  const vals = rows.map(r => r.pm2_5).filter(v => v != null);
  const avg = vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  const mx = vals.length ? Math.max(...vals) : null;
  const mn = vals.length ? Math.min(...vals) : null;
  document.getElementById('trendStats').innerHTML = `
    <div class="stat-tile"><div class="val">${fmt(avg)}</div><div class="lbl">ค่าเฉลี่ย</div></div>
    <div class="stat-tile"><div class="val">${fmt(mx)}</div><div class="lbl">สูงสุด</div></div>
    <div class="stat-tile"><div class="val">${fmt(mn)}</div><div class="lbl">ต่ำสุด</div></div>
    <div class="stat-tile"><div class="val">${vals.length}</div><div class="lbl">จำนวนจุดข้อมูล</div></div>`;
}

/* ---------------------- Refresh all ---------------------- */
async function refreshAll() {
  const btn = document.getElementById('refreshBtn');
  btn.classList.add('spin');
  await Promise.all([
    loadLatest(),
    loadHistory(),
    loadTrend(currentRange, 'trendChart'),
  ]);
  setTimeout(() => btn.classList.remove('spin'), 400);
}

/* ---------------------- View switching ---------------------- */
function switchView(view) {
  document.querySelectorAll('.nav-item').forEach(n =>
    n.classList.toggle('active', n.dataset.view === view));
  document.querySelectorAll('.view').forEach(v =>
    v.classList.toggle('active', v.id === 'view-' + view));

  if (view === 'trend') loadTrendFull(currentRange);
  if (view === 'history') loadHistoryFull();
}

/* ---------------------- Init ---------------------- */
function startAutoRefresh() {
  if (refreshTimer) clearInterval(refreshTimer);
  const sec = (settings.refreshInterval || 30) * 1000;
  refreshTimer = setInterval(refreshAll, sec);
}

function init() {
  tickClock();
  setInterval(tickClock, 1000);

  // nav
  document.getElementById('nav').addEventListener('click', e => {
    const btn = e.target.closest('.nav-item');
    if (btn) switchView(btn.dataset.view);
  });

  // refresh
  document.getElementById('refreshBtn').addEventListener('click', refreshAll);

  // range tabs (dashboard)
  document.getElementById('rangeTabs').addEventListener('click', e => {
    const t = e.target.closest('.range-tab'); if (!t) return;
    document.querySelectorAll('#rangeTabs .range-tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    currentRange = t.dataset.range;
    loadTrend(currentRange, 'trendChart');
  });
  // range tabs (trend full)
  document.getElementById('rangeTabs2').addEventListener('click', e => {
    const t = e.target.closest('.range-tab'); if (!t) return;
    document.querySelectorAll('#rangeTabs2 .range-tab').forEach(x => x.classList.remove('active'));
    t.classList.add('active');
    loadTrendFull(t.dataset.range);
  });

  // metric select
  document.getElementById('metricSelect').addEventListener('change', () =>
    loadTrend(currentRange, 'trendChart'));

  // history limit
  document.getElementById('historyLimit').addEventListener('change', loadHistoryFull);

  // settings
  const ri = document.getElementById('refreshInterval');
  ri.value = settings.refreshInterval || 30;
  document.getElementById('saveSettings').addEventListener('click', () => {
    settings.refreshInterval = Math.max(5, Number(ri.value) || 30);
    localStorage.setItem('pm25_settings', JSON.stringify(settings));
    startAutoRefresh();
    alert('บันทึกการตั้งค่าแล้ว');
  });

  // redraw chart on resize
  window.addEventListener('resize', () => loadTrend(currentRange, 'trendChart'));

  refreshAll();
  startAutoRefresh();
}

document.addEventListener('DOMContentLoaded', init);

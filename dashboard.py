"""
Panel web para el Funding Rate Arbitrage Bot
Corre en paralelo al bot principal
"""

import os
import json
import threading
from datetime import datetime
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)

DATA_DIR = os.getenv("DATA_DIR", "data")

# ─── Helpers ─────────────────────────────────────────────────────────────────

def load_json(filename: str) -> list | dict:
    path = os.path.join(DATA_DIR, filename)
    try:
        with open(path) as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return [] if filename.endswith("s.json") else {}


def load_log_tail(n: int = 80) -> list[str]:
    try:
        with open("logs/bot.log") as f:
            lines = f.readlines()
        return [l.rstrip() for l in lines[-n:]]
    except FileNotFoundError:
        return ["Sin logs disponibles aún."]


# ─── API endpoints ────────────────────────────────────────────────────────────

@app.route("/api/positions")
def api_positions():
    return jsonify(load_json("positions.json"))


@app.route("/api/trades")
def api_trades():
    trades = load_json("trades.json")
    return jsonify(list(reversed(trades)) if isinstance(trades, list) else [])


@app.route("/api/summary")
def api_summary():
    trades = load_json("trades.json")
    positions = load_json("positions.json")

    closed = [t for t in trades if isinstance(t, dict) and t.get("status") == "closed"]
    open_pos = positions if isinstance(positions, list) else []

    total_pnl     = sum(t.get("pnl_net", 0) or 0 for t in closed)
    total_funding = sum(t.get("funding_collected", 0) for t in closed)
    win_trades    = [t for t in closed if (t.get("pnl_net") or 0) > 0]
    win_rate      = (len(win_trades) / len(closed) * 100) if closed else 0

    capital_in_use = sum(p.get("capital", 0) for p in open_pos)

    return jsonify({
        "total_pnl":       round(total_pnl, 4),
        "total_funding":   round(total_funding, 4),
        "closed_trades":   len(closed),
        "open_positions":  len(open_pos),
        "win_rate":        round(win_rate, 1),
        "capital_in_use":  capital_in_use,
        "mode":            os.getenv("PAPER_TRADING", "true"),
    })


@app.route("/api/logs")
def api_logs():
    return jsonify(load_log_tail(80))


# ─── Main HTML ────────────────────────────────────────────────────────────────

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Funding Bot — Panel</title>
<style>
  *, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
  :root {
    --bg: #0f1117; --surface: #1a1d27; --surface2: #22263a;
    --border: rgba(255,255,255,0.08); --text: #e8eaf0;
    --muted: #8b90a0; --green: #4ade80; --red: #f87171;
    --amber: #fbbf24; --purple: #a78bfa; --blue: #60a5fa;
  }
  body { background: var(--bg); color: var(--text); font-family: system-ui, sans-serif; font-size: 14px; }
  a { color: inherit; text-decoration: none; }

  /* Layout */
  .topbar { display: flex; align-items: center; justify-content: space-between; padding: 14px 24px; background: var(--surface); border-bottom: 1px solid var(--border); }
  .topbar h1 { font-size: 15px; font-weight: 600; display: flex; align-items: center; gap: 8px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: var(--green); display: inline-block; animation: pulse 2s infinite; }
  @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:.4} }
  .badge-mode { font-size: 11px; padding: 3px 10px; border-radius: 20px; font-weight: 600; }
  .badge-paper { background: rgba(251,191,36,0.15); color: var(--amber); }
  .badge-real  { background: rgba(248,113,113,0.15); color: var(--red); }
  .last-update { font-size: 12px; color: var(--muted); }

  .container { max-width: 1200px; margin: 0 auto; padding: 24px; }

  /* Metric cards */
  .metrics { display: grid; grid-template-columns: repeat(auto-fit, minmax(160px, 1fr)); gap: 12px; margin-bottom: 24px; }
  .metric { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; padding: 16px; }
  .metric-label { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: .05em; margin-bottom: 8px; }
  .metric-value { font-size: 24px; font-weight: 600; }
  .green { color: var(--green); }
  .red   { color: var(--red); }
  .muted { color: var(--muted); }

  /* Tabs */
  .tabs { display: flex; gap: 4px; margin-bottom: 16px; border-bottom: 1px solid var(--border); padding-bottom: 0; }
  .tab { padding: 8px 16px; font-size: 13px; cursor: pointer; color: var(--muted); border-bottom: 2px solid transparent; margin-bottom: -1px; }
  .tab.active { color: var(--text); border-bottom-color: var(--purple); }
  .tab-content { display: none; }
  .tab-content.active { display: block; }

  /* Tables */
  .card { background: var(--surface); border: 1px solid var(--border); border-radius: 10px; overflow: hidden; margin-bottom: 20px; }
  table { width: 100%; border-collapse: collapse; }
  th { font-size: 11px; text-transform: uppercase; letter-spacing: .05em; color: var(--muted); padding: 10px 16px; text-align: left; border-bottom: 1px solid var(--border); font-weight: 500; }
  td { padding: 12px 16px; border-bottom: 1px solid var(--border); font-size: 13px; }
  tr:last-child td { border-bottom: none; }
  tr:hover td { background: var(--surface2); }
  .empty { padding: 32px; text-align: center; color: var(--muted); }

  /* Log */
  .log-box { background: #0a0c10; border: 1px solid var(--border); border-radius: 10px; padding: 16px; font-family: monospace; font-size: 12px; line-height: 1.7; max-height: 420px; overflow-y: auto; color: #a0aec0; }
  .log-info  { color: #68d391; }
  .log-warn  { color: var(--amber); }
  .log-error { color: var(--red); }

  /* Pos card */
  .pos-card { background: var(--surface2); border: 1px solid rgba(74,222,128,0.2); border-radius: 10px; padding: 14px 18px; margin-bottom: 10px; display: grid; grid-template-columns: 100px 1fr 120px 120px; gap: 10px; align-items: center; }
  .pos-symbol { font-weight: 600; font-size: 15px; }
  .pos-detail { font-size: 12px; color: var(--muted); line-height: 1.6; }
  .pos-funding { font-size: 16px; font-weight: 600; }

  /* Refresh btn */
  .btn-refresh { background: var(--surface2); border: 1px solid var(--border); color: var(--text); padding: 6px 14px; border-radius: 8px; cursor: pointer; font-size: 12px; }
  .btn-refresh:hover { background: var(--surface); }
</style>
</head>
<body>

<div class="topbar">
  <h1><span class="dot"></span> Funding Rate Bot</h1>
  <div style="display:flex;align-items:center;gap:12px;">
    <span id="badge-mode" class="badge-mode badge-paper">PAPER</span>
    <span class="last-update" id="last-update">—</span>
    <button class="btn-refresh" onclick="loadAll()">↻ Actualizar</button>
  </div>
</div>

<div class="container">

  <div class="metrics" id="metrics">
    <div class="metric"><div class="metric-label">PnL Total</div><div class="metric-value muted" id="m-pnl">—</div></div>
    <div class="metric"><div class="metric-label">Funding cobrado</div><div class="metric-value muted" id="m-funding">—</div></div>
    <div class="metric"><div class="metric-label">Trades cerrados</div><div class="metric-value muted" id="m-closed">—</div></div>
    <div class="metric"><div class="metric-label">Posiciones abiertas</div><div class="metric-value muted" id="m-open">—</div></div>
    <div class="metric"><div class="metric-label">Win rate</div><div class="metric-value muted" id="m-winrate">—</div></div>
    <div class="metric"><div class="metric-label">Capital en uso</div><div class="metric-value muted" id="m-capital">—</div></div>
  </div>

  <div class="tabs">
    <div class="tab active" onclick="switchTab('positions')">Posiciones abiertas</div>
    <div class="tab" onclick="switchTab('history')">Historial</div>
    <div class="tab" onclick="switchTab('logs')">Logs en vivo</div>
  </div>

  <!-- Posiciones -->
  <div id="tab-positions" class="tab-content active">
    <div id="positions-container"><div class="empty">Cargando...</div></div>
  </div>

  <!-- Historial -->
  <div id="tab-history" class="tab-content">
    <div class="card">
      <table id="trades-table">
        <thead><tr>
          <th>Par</th><th>Capital</th><th>Rate entrada</th>
          <th>Apertura</th><th>Cierre</th><th>Funding</th><th>PnL neto</th><th>Modo</th>
        </tr></thead>
        <tbody id="trades-body"><tr><td colspan="8" class="empty">Cargando...</td></tr></tbody>
      </table>
    </div>
  </div>

  <!-- Logs -->
  <div id="tab-logs" class="tab-content">
    <div class="log-box" id="log-box">Cargando logs...</div>
  </div>

</div>

<script>
function switchTab(name) {
  document.querySelectorAll('.tab').forEach((t,i) => {
    const names = ['positions','history','logs'];
    t.classList.toggle('active', names[i] === name);
  });
  document.querySelectorAll('.tab-content').forEach(c => c.classList.remove('active'));
  document.getElementById('tab-' + name).classList.add('active');
  if(name === 'logs') loadLogs();
}

async function fetchJson(url) {
  const r = await fetch(url);
  return r.json();
}

function fmt(v, digits=4) {
  if(v === null || v === undefined) return '—';
  const n = parseFloat(v);
  const s = n >= 0 ? '+' : '';
  return s + n.toFixed(digits);
}

function fmtDate(iso) {
  if(!iso) return '—';
  return new Date(iso).toLocaleString('es-AR', {day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'});
}

async function loadSummary() {
  const d = await fetchJson('/api/summary');
  const pnl = parseFloat(d.total_pnl);
  document.getElementById('m-pnl').textContent = fmt(d.total_pnl, 2) + ' USDT';
  document.getElementById('m-pnl').className = 'metric-value ' + (pnl >= 0 ? 'green' : 'red');
  document.getElementById('m-funding').textContent = '+$' + parseFloat(d.total_funding).toFixed(4);
  document.getElementById('m-funding').className = 'metric-value green';
  document.getElementById('m-closed').textContent = d.closed_trades;
  document.getElementById('m-closed').className = 'metric-value';
  document.getElementById('m-open').textContent = d.open_positions;
  document.getElementById('m-open').className = 'metric-value ' + (d.open_positions > 0 ? 'green' : 'muted');
  document.getElementById('m-winrate').textContent = d.win_rate + '%';
  document.getElementById('m-winrate').className = 'metric-value ' + (d.win_rate >= 50 ? 'green' : 'red');
  document.getElementById('m-capital').textContent = '$' + d.capital_in_use.toLocaleString();
  document.getElementById('m-capital').className = 'metric-value';

  const isReal = d.mode === 'false';
  const badge = document.getElementById('badge-mode');
  badge.textContent = isReal ? 'REAL' : 'PAPER';
  badge.className = 'badge-mode ' + (isReal ? 'badge-real' : 'badge-paper');
}

async function loadPositions() {
  const positions = await fetchJson('/api/positions');
  const cont = document.getElementById('positions-container');
  if(!positions.length) {
    cont.innerHTML = '<div class="empty">Sin posiciones abiertas actualmente</div>';
    return;
  }
  cont.innerHTML = positions.map(p => `
    <div class="pos-card">
      <div>
        <div class="pos-symbol">${p.symbol}</div>
        <div style="font-size:11px;color:#4ade80;margin-top:2px;">ACTIVA</div>
      </div>
      <div class="pos-detail">
        Capital: $${p.capital} USDT<br>
        Rate entrada: ${parseFloat(p.entry_rate || 0).toFixed(4)}%<br>
        Precio entrada: $${parseFloat(p.entry_price || 0).toLocaleString()}<br>
        Abierta: ${fmtDate(p.opened_at)}
      </div>
      <div>
        <div style="font-size:11px;color:var(--muted);margin-bottom:4px;">Funding acumulado</div>
        <div class="pos-funding green">+$${parseFloat(p.funding_collected || 0).toFixed(4)}</div>
      </div>
      <div style="font-size:12px;color:var(--muted);">
        Spot: Bybit<br>Short: Binance<br>Delta neutral ✓
      </div>
    </div>`).join('');
}

async function loadTrades() {
  const trades = await fetchJson('/api/trades');
  const tbody = document.getElementById('trades-body');
  if(!trades.length) {
    tbody.innerHTML = '<tr><td colspan="8" class="empty">Sin trades cerrados aún</td></tr>';
    return;
  }
  tbody.innerHTML = trades.map(t => {
    const pnl = parseFloat(t.pnl_net || 0);
    const cls = pnl >= 0 ? 'green' : 'red';
    return `<tr>
      <td><strong>${t.symbol}</strong></td>
      <td>$${t.capital}</td>
      <td>${parseFloat(t.rate_at_open || 0).toFixed(4)}%</td>
      <td>${fmtDate(t.opened_at)}</td>
      <td>${fmtDate(t.closed_at)}</td>
      <td class="green">+$${parseFloat(t.funding_collected || 0).toFixed(4)}</td>
      <td class="${cls}">${fmt(t.pnl_net, 4)} USDT</td>
      <td style="color:var(--muted)">${t.mode || '—'}</td>
    </tr>`;
  }).join('');
}

async function loadLogs() {
  const lines = await fetchJson('/api/logs');
  const box = document.getElementById('log-box');
  box.innerHTML = lines.map(l => {
    let cls = '';
    if(l.includes('[ERROR]')) cls = 'log-error';
    else if(l.includes('[WARNING]')) cls = 'log-warn';
    else if(l.includes('[INFO]')) cls = 'log-info';
    return `<div class="${cls}">${l}</div>`;
  }).join('');
  box.scrollTop = box.scrollHeight;
}

async function loadAll() {
  await Promise.all([loadSummary(), loadPositions(), loadTrades()]);
  document.getElementById('last-update').textContent =
    'Actualizado: ' + new Date().toLocaleTimeString('es-AR');
}

loadAll();
setInterval(loadAll, 15000);
setInterval(() => {
  const active = document.querySelector('.tab.active');
  if(active && active.textContent.includes('Logs')) loadLogs();
}, 10000);
</script>
</body>
</html>"""


@app.route("/")
def index():
    return render_template_string(HTML)


# ─── Run ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

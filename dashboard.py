"""
Panel web — Funding Rate Bot
Con verificación de auth y balance de OKX y Bitget
"""

import os
import json
from flask import Flask, jsonify, render_template_string

app = Flask(__name__)
DATA_DIR = os.getenv("DATA_DIR", "data")

def load_json(name, default=None):
    try:
        with open(os.path.join(DATA_DIR, name)) as f:
            return json.load(f)
    except:
        return default if default is not None else []

def load_log_tail(n=100):
    try:
        with open("logs/bot.log") as f:
            return [l.rstrip() for l in f.readlines()[-n:]]
    except:
        return ["Sin logs aún."]

@app.route("/api/auth")
def api_auth():
    return jsonify(load_json("auth_status.json", {}))

@app.route("/api/positions")
def api_positions():
    return jsonify(load_json("positions.json"))

@app.route("/api/trades")
def api_trades():
    t = load_json("trades.json")
    return jsonify(list(reversed(t)) if isinstance(t, list) else [])

@app.route("/api/summary")
def api_summary():
    trades = load_json("trades.json")
    positions = load_json("positions.json")
    closed = [t for t in trades if isinstance(t, dict) and t.get("status") == "closed"]
    total_pnl = sum(t.get("pnl_net") or 0 for t in closed)
    total_funding = sum(t.get("funding_collected", 0) for t in closed)
    win = [t for t in closed if (t.get("pnl_net") or 0) > 0]
    capital_in_use = sum(p.get("capital", 0) for p in positions)
    return jsonify({
        "total_pnl": round(total_pnl, 4),
        "total_funding": round(total_funding, 4),
        "closed_trades": len(closed),
        "open_positions": len(positions),
        "win_rate": round(len(win) / len(closed) * 100, 1) if closed else 0,
        "capital_in_use": capital_in_use,
        "spot_perp_trades": len([t for t in closed if t.get("strategy") == "spot_perp"]),
        "spread_trades": len([t for t in closed if t.get("strategy") == "spread"]),
        "mode": os.getenv("PAPER_TRADING", "true"),
    })

@app.route("/api/logs")
def api_logs():
    return jsonify(load_log_tail(100))

HTML = """<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Funding Bot</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f1117;--s:#1a1d27;--s2:#22263a;--b:rgba(255,255,255,0.08);--t:#e8eaf0;--m:#8b90a0;--green:#4ade80;--red:#f87171;--amber:#fbbf24;--purple:#a78bfa;--blue:#60a5fa}
body{background:var(--bg);color:var(--t);font-family:system-ui,sans-serif;font-size:14px}
.topbar{display:flex;align-items:center;justify-content:space-between;padding:14px 24px;background:var(--s);border-bottom:1px solid var(--b);flex-wrap:wrap;gap:10px}
.topbar h1{font-size:15px;font-weight:600;display:flex;align-items:center;gap:8px}
.pulse{width:8px;height:8px;border-radius:50%;background:var(--green);display:inline-block;animation:pulse 2s infinite}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:.4}}
.badge{font-size:11px;padding:3px 10px;border-radius:20px;font-weight:600}
.badge-paper{background:rgba(251,191,36,.15);color:var(--amber)}
.badge-real{background:rgba(248,113,113,.15);color:var(--red)}
.badge-demo{background:rgba(96,165,250,.15);color:var(--blue)}
.badge-strat{background:rgba(167,139,250,.15);color:var(--purple);font-size:10px;padding:2px 7px;border-radius:4px;font-weight:500}
.container{max-width:1250px;margin:0 auto;padding:24px}

/* Auth cards */
.auth-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(280px,1fr));gap:12px;margin-bottom:24px}
.auth-card{background:var(--s);border:1px solid var(--b);border-radius:12px;padding:18px}
.auth-card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:14px}
.auth-name{font-size:15px;font-weight:600}
.auth-status{display:flex;align-items:center;gap:6px;font-size:12px}
.auth-dot{width:9px;height:9px;border-radius:50%}
.auth-dot-ok{background:var(--green);box-shadow:0 0 6px rgba(74,222,128,.5)}
.auth-dot-err{background:var(--red)}
.auth-dot-nokey{background:var(--m)}
.auth-dot-load{background:var(--amber);animation:pulse 1s infinite}
.auth-row{display:flex;justify-content:space-between;align-items:center;padding:6px 0;border-bottom:1px solid var(--b);font-size:13px}
.auth-row:last-child{border-bottom:none}
.auth-label{color:var(--m)}
.auth-value{font-weight:500}
.auth-error{font-size:12px;color:var(--red);margin-top:8px;padding:8px;background:rgba(248,113,113,.08);border-radius:6px;word-break:break-word}

.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:24px}
.metric{background:var(--s);border:1px solid var(--b);border-radius:10px;padding:16px}
.metric-label{font-size:11px;color:var(--m);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px}
.metric-value{font-size:22px;font-weight:600}
.green{color:var(--green)}.red{color:var(--red)}.muted{color:var(--m)}
.tabs{display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid var(--b)}
.tab{padding:8px 16px;font-size:13px;cursor:pointer;color:var(--m);border-bottom:2px solid transparent;margin-bottom:-1px;background:none;border-top:none;border-left:none;border-right:none}
.tab.active{color:var(--t);border-bottom-color:var(--purple)}
.tab-content{display:none}.tab-content.active{display:block}
.card{background:var(--s);border:1px solid var(--b);border-radius:10px;overflow:hidden;margin-bottom:20px}
table{width:100%;border-collapse:collapse}
th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--m);padding:10px 14px;text-align:left;border-bottom:1px solid var(--b);font-weight:500;white-space:nowrap}
td{padding:11px 14px;border-bottom:1px solid var(--b);font-size:13px}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--s2)}
.empty{padding:32px;text-align:center;color:var(--m)}
.log-box{background:#0a0c10;border:1px solid var(--b);border-radius:10px;padding:16px;font-family:monospace;font-size:12px;line-height:1.7;max-height:500px;overflow-y:auto;color:#a0aec0}
.log-info{color:#68d391}.log-warn{color:var(--amber)}.log-error{color:var(--red)}
.pos-card{background:var(--s2);border:1px solid rgba(74,222,128,.2);border-radius:10px;padding:14px 18px;margin-bottom:10px}
.pos-grid{display:grid;grid-template-columns:120px 1fr 140px;gap:10px;align-items:center}
.pos-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-top:10px;padding-top:10px;border-top:1px solid var(--b)}
.pos-stat-label{font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.pos-stat-value{font-size:14px;font-weight:600}
.btn{background:var(--s2);border:1px solid var(--b);color:var(--t);padding:6px 14px;border-radius:8px;cursor:pointer;font-size:12px}
.btn:hover{background:var(--s)}
.divider{border:none;border-top:1px solid var(--b);margin:1rem 0}
</style>
</head>
<body>

<div class="topbar">
  <h1><span class="pulse"></span> Funding Rate Bot</h1>
  <div style="display:flex;align-items:center;gap:12px;flex-wrap:wrap">
    <span id="badge-mode" class="badge badge-paper">PAPER</span>
    <span style="font-size:12px;color:var(--m)" id="last-update">—</span>
    <button class="btn" onclick="loadAll()">↻ Actualizar</button>
  </div>
</div>

<div class="container">

  <!-- Auth section -->
  <div style="font-size:11px;font-weight:500;color:var(--m);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">
    Estado de conexión — exchanges operativos
  </div>
  <div class="auth-grid" id="auth-grid">
    <div class="auth-card"><div style="color:var(--m);font-size:13px">Verificando conexión...</div></div>
  </div>

  <!-- Metrics -->
  <div class="metrics">
    <div class="metric"><div class="metric-label">PnL Total</div><div class="metric-value muted" id="m-pnl">—</div></div>
    <div class="metric"><div class="metric-label">Funding cobrado</div><div class="metric-value muted" id="m-funding">—</div></div>
    <div class="metric"><div class="metric-label">Posiciones abiertas</div><div class="metric-value muted" id="m-open">—</div></div>
    <div class="metric"><div class="metric-label">Capital en uso</div><div class="metric-value muted" id="m-capital">—</div></div>
    <div class="metric"><div class="metric-label">Win rate</div><div class="metric-value muted" id="m-win">—</div></div>
    <div class="metric"><div class="metric-label">Trades cerrados</div><div class="metric-value muted" id="m-closed">—</div></div>
  </div>

  <div class="tabs">
    <button class="tab active" onclick="switchTab('positions')">Posiciones abiertas</button>
    <button class="tab" onclick="switchTab('history')">Historial</button>
    <button class="tab" onclick="switchTab('logs')">Logs en vivo</button>
  </div>

  <div id="tab-positions" class="tab-content active">
    <div id="positions-container"><div class="empty">Cargando...</div></div>
  </div>

  <div id="tab-history" class="tab-content">
    <div class="card">
      <table>
        <thead><tr>
          <th>Par</th><th>Estrategia</th><th>Long en</th><th>Short en</th>
          <th>Capital</th><th>Rate</th><th>Modo</th><th>Apertura</th><th>Cierre</th>
          <th>Funding</th><th>PnL neto</th>
        </tr></thead>
        <tbody id="trades-body"><tr><td colspan="11" class="empty">Cargando...</td></tr></tbody>
      </table>
    </div>
  </div>

  <div id="tab-logs" class="tab-content">
    <div class="log-box" id="log-box">Cargando logs...</div>
  </div>
</div>

<script>
async function fetchJson(url){try{const r=await fetch(url);return r.json()}catch{return null}}
function fmt(v,d=4){if(v===null||v===undefined)return'—';const n=parseFloat(v);return(n>=0?'+':'')+n.toFixed(d)}
function fmtDate(iso){if(!iso)return'—';return new Date(iso).toLocaleString('es-AR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}

async function loadAuth(){
  const d=await fetchJson('/api/auth');
  if(!d){return;}
  const grid=document.getElementById('auth-grid');
  const exchanges=['okx','bitget'];
  const labels={okx:'OKX',bitget:'Bitget'};

  grid.innerHTML=exchanges.map(ex=>{
    const info=d[ex];
    if(!info)return`<div class="auth-card"><div class="auth-name">${labels[ex]}</div><div style="color:var(--m);font-size:13px;margin-top:8px">Sin datos aún</div></div>`;

    let dotCls,statusText,statusColor;
    if(info.status==='ok'){
      dotCls='auth-dot-ok';statusText='Conectado';statusColor='var(--green)';
    } else if(info.status==='error'){
      dotCls='auth-dot-err';statusText='Error de autenticación';statusColor='var(--red)';
    } else {
      dotCls='auth-dot-nokey';statusText='Sin API key';statusColor='var(--m)';
    }

    const isDemo=info.demo;
    const modeBadge=isDemo
      ?`<span class="badge badge-demo" style="font-size:10px">DEMO</span>`
      :`<span class="badge badge-real" style="font-size:10px">REAL</span>`;

    let body='';
    if(info.status==='ok'){
      body=`
        <div class="auth-row"><span class="auth-label">Balance libre</span><span class="auth-value green">$${info.free?.toLocaleString()||'—'} USDT</span></div>
        <div class="auth-row"><span class="auth-label">Balance total</span><span class="auth-value">$${info.total?.toLocaleString()||'—'} USDT</span></div>
        <div class="auth-row"><span class="auth-label">Modo</span><span class="auth-value">${modeBadge}</span></div>
        <div class="auth-row"><span class="auth-label">Verificado</span><span class="auth-value" style="color:var(--m);font-size:12px">${fmtDate(d.checked_at)}</span></div>`;
    } else if(info.status==='error'){
      body=`
        <div class="auth-row"><span class="auth-label">Modo</span><span class="auth-value">${modeBadge}</span></div>
        <div class="auth-error">⚠ ${info.error||'Error desconocido'}</div>`;
    } else {
      body=`<div style="font-size:13px;color:var(--m);margin-top:8px">Cargá las API keys en Railway Variables para activar este exchange.</div>`;
    }

    return`<div class="auth-card">
      <div class="auth-card-header">
        <div class="auth-name">${labels[ex]}</div>
        <div class="auth-status">
          <span class="auth-dot ${dotCls}"></span>
          <span style="color:${statusColor}">${statusText}</span>
        </div>
      </div>
      ${body}
    </div>`;
  }).join('');
}

async function loadSummary(){
  const d=await fetchJson('/api/summary');
  if(!d)return;
  const pnl=parseFloat(d.total_pnl);
  document.getElementById('m-pnl').textContent=fmt(d.total_pnl,2)+' USDT';
  document.getElementById('m-pnl').className='metric-value '+(pnl>=0?'green':'red');
  document.getElementById('m-funding').textContent='+$'+parseFloat(d.total_funding).toFixed(4);
  document.getElementById('m-funding').className='metric-value green';
  document.getElementById('m-open').textContent=d.open_positions;
  document.getElementById('m-open').className='metric-value '+(d.open_positions>0?'green':'muted');
  document.getElementById('m-capital').textContent='$'+d.capital_in_use.toLocaleString();
  document.getElementById('m-capital').className='metric-value';
  document.getElementById('m-win').textContent=d.win_rate+'%';
  document.getElementById('m-win').className='metric-value '+(d.win_rate>=50?'green':'red');
  document.getElementById('m-closed').textContent=d.closed_trades;
  document.getElementById('m-closed').className='metric-value';
  const isReal=d.mode==='false';
  const badge=document.getElementById('badge-mode');
  badge.textContent=isReal?'REAL':'PAPER';
  badge.className='badge '+(isReal?'badge-real':'badge-paper');
}

async function loadPositions(){
  const positions=await fetchJson('/api/positions');
  const cont=document.getElementById('positions-container');
  if(!positions?.length){cont.innerHTML='<div class="empty">Sin posiciones abiertas</div>';return;}
  cont.innerHTML=positions.map(p=>{
    const strat=p.strategy==='spread'?'Spread inter-exchange':'Spot / Perp';
    const stratColor=p.strategy==='spread'?'var(--purple)':'var(--blue)';
    const dailyEst=p.capital*(p.entry_rate/100)*24;
    const monthlyEst=dailyEst*30;
    const modeBadge=p.mode==='demo'
      ?`<span class="badge badge-demo" style="font-size:10px">DEMO</span>`
      :p.mode==='real'
      ?`<span class="badge badge-real" style="font-size:10px">REAL</span>`
      :`<span class="badge badge-paper" style="font-size:10px">PAPER</span>`;
    return`<div class="pos-card">
      <div class="pos-grid">
        <div>
          <div style="font-weight:600;font-size:15px">${p.spot_symbol||p.symbol}</div>
          <div style="font-size:11px;color:${stratColor};margin-top:3px;font-weight:500">${strat}</div>
          <div style="margin-top:5px">${modeBadge}</div>
        </div>
        <div style="font-size:12px;color:var(--m)">
          Long: <strong style="color:var(--t)">${p.long_exchange}</strong> &nbsp;·&nbsp;
          Short: <strong style="color:var(--t)">${p.short_exchange}</strong><br>
          Capital: $${p.capital} · Rate entrada: ${parseFloat(p.entry_rate||0).toFixed(4)}%<br>
          Abierta: ${fmtDate(p.opened_at)}
        </div>
        <div style="text-align:right">
          <div style="font-size:11px;color:var(--m);margin-bottom:3px">Funding acumulado</div>
          <div style="font-size:16px;font-weight:600;color:var(--green)">+$${parseFloat(p.funding_collected||0).toFixed(4)}</div>
        </div>
      </div>
      <div class="pos-stats">
        <div><div class="pos-stat-label">Spread</div><div class="pos-stat-value" style="color:var(--green)">${parseFloat(p.entry_rate||0).toFixed(4)}%</div></div>
        <div><div class="pos-stat-label">Est. diario</div><div class="pos-stat-value green">+$${dailyEst.toFixed(2)}</div></div>
        <div><div class="pos-stat-label">Est. mensual</div><div class="pos-stat-value green">+$${monthlyEst.toFixed(2)}</div></div>
        <div><div class="pos-stat-label">Delta neutral</div><div class="pos-stat-value" style="color:var(--green)">✓</div></div>
      </div>
    </div>`;
  }).join('');
}

async function loadTrades(){
  const trades=await fetchJson('/api/trades');
  const tbody=document.getElementById('trades-body');
  if(!trades?.length){tbody.innerHTML='<tr><td colspan="11" class="empty">Sin trades cerrados aún</td></tr>';return;}
  tbody.innerHTML=trades.map(t=>{
    const pnl=parseFloat(t.pnl_net||0);
    const strat=t.strategy==='spread'?'Spread':'Spot/Perp';
    const modeBadge=t.mode==='demo'
      ?`<span class="badge badge-demo" style="font-size:10px">DEMO</span>`
      :t.mode==='real'
      ?`<span class="badge badge-real" style="font-size:10px">REAL</span>`
      :`<span class="badge badge-paper" style="font-size:10px">PAPER</span>`;
    return`<tr>
      <td><strong>${t.symbol}</strong></td>
      <td><span class="badge-strat">${strat}</span></td>
      <td>${t.long_exchange||'—'}</td>
      <td>${t.short_exchange||'—'}</td>
      <td>$${t.capital}</td>
      <td>${parseFloat(t.rate_at_open||0).toFixed(4)}%</td>
      <td>${modeBadge}</td>
      <td>${fmtDate(t.opened_at)}</td>
      <td>${fmtDate(t.closed_at)}</td>
      <td class="green">+$${parseFloat(t.funding_collected||0).toFixed(4)}</td>
      <td class="${pnl>=0?'green':'red'}">${fmt(t.pnl_net,4)} USDT</td>
    </tr>`;
  }).join('');
}

async function loadLogs(){
  const lines=await fetchJson('/api/logs');
  if(!lines)return;
  const box=document.getElementById('log-box');
  box.innerHTML=lines.map(l=>{
    let cls='';
    if(l.includes('[ERROR]'))cls='log-error';
    else if(l.includes('[WARNING]'))cls='log-warn';
    else if(l.includes('[INFO]'))cls='log-info';
    return`<div class="${cls}">${l}</div>`;
  }).join('');
  box.scrollTop=box.scrollHeight;
}

function switchTab(name){
  document.querySelectorAll('.tab').forEach((t,i)=>{
    t.classList.toggle('active',['positions','history','logs'][i]===name);
  });
  document.querySelectorAll('.tab-content').forEach(c=>c.classList.remove('active'));
  document.getElementById('tab-'+name).classList.add('active');
  if(name==='logs')loadLogs();
}

async function loadAll(){
  await Promise.all([loadAuth(),loadSummary(),loadPositions(),loadTrades()]);
  document.getElementById('last-update').textContent='↻ '+new Date().toLocaleTimeString('es-AR');
}

loadAll();
setInterval(loadAll,15000);
setInterval(()=>{
  if(document.querySelector('.tab.active')?.textContent.includes('Logs'))loadLogs();
},10000);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

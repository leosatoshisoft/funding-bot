"""
Panel web — Funding Rate Bot
Pestañas: Auth | Posiciones | Oportunidades | Historial | Logs
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
    trades    = load_json("trades.json")
    positions = load_json("positions.json")
    closed    = [t for t in trades if isinstance(t, dict) and t.get("status") == "closed"]
    open_t    = [t for t in trades if isinstance(t, dict) and t.get("status") == "open"]
    total_pnl     = sum(t.get("pnl_net") or 0 for t in closed)
    funding_cl    = sum(t.get("funding_collected", 0) for t in closed)
    funding_op    = sum(t.get("funding_collected", 0) for t in open_t)
    win           = [t for t in closed if (t.get("pnl_net") or 0) > 0]
    capital_in_use = sum(p.get("capital", 0) for p in positions)
    return jsonify({
        "total_pnl":        round(total_pnl, 4),
        "total_funding":    round(funding_cl + funding_op, 4),
        "closed_trades":    len(closed),
        "open_positions":   len(positions),
        "win_rate":         round(len(win) / len(closed) * 100, 1) if closed else 0,
        "capital_in_use":   capital_in_use,
        "spread_trades":    len([t for t in closed if t.get("strategy") == "spread"]),
        "mode":             os.getenv("PAPER_TRADING", "true"),
    })

@app.route("/api/logs")
def api_logs():
    return jsonify(load_log_tail(100))

HTML = r"""<!DOCTYPE html>
<html lang="es">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Funding Bot</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
:root{--bg:#0f1117;--s:#1a1d27;--s2:#22263a;--b:rgba(255,255,255,0.08);--t:#e8eaf0;--m:#8b90a0;--green:#4ade80;--red:#f87171;--amber:#fbbf24;--purple:#a78bfa;--blue:#60a5fa;--teal:#2dd4bf}
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
.container{max-width:1280px;margin:0 auto;padding:24px}
.auth-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(230px,1fr));gap:12px;margin-bottom:24px}
.auth-card{background:var(--s);border:1px solid var(--b);border-radius:12px;padding:16px}
.auth-card-header{display:flex;align-items:center;justify-content:space-between;margin-bottom:12px}
.auth-name{font-size:15px;font-weight:600}
.auth-status{display:flex;align-items:center;gap:6px;font-size:12px}
.auth-dot{width:9px;height:9px;border-radius:50%}
.auth-dot-ok{background:var(--green);box-shadow:0 0 6px rgba(74,222,128,.5)}
.auth-dot-err{background:var(--red)}
.auth-dot-nokey{background:var(--m)}
.auth-row{display:flex;justify-content:space-between;padding:5px 0;border-bottom:1px solid var(--b);font-size:12px}
.auth-row:last-child{border-bottom:none}
.auth-label{color:var(--m)}
.auth-error{font-size:11px;color:var(--red);margin-top:8px;padding:8px;background:rgba(248,113,113,.08);border-radius:6px;word-break:break-word}
.metrics{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:12px;margin-bottom:20px}
.metric{background:var(--s);border:1px solid var(--b);border-radius:10px;padding:16px}
.metric-label{font-size:11px;color:var(--m);text-transform:uppercase;letter-spacing:.05em;margin-bottom:8px}
.metric-value{font-size:22px;font-weight:600}
.green{color:var(--green)}.red{color:var(--red)}.muted{color:var(--m)}
.tabs{display:flex;gap:4px;margin-bottom:16px;border-bottom:1px solid var(--b);overflow-x:auto}
.tab{padding:8px 16px;font-size:13px;cursor:pointer;color:var(--m);border-bottom:2px solid transparent;margin-bottom:-1px;background:none;border-top:none;border-left:none;border-right:none;white-space:nowrap}
.tab.active{color:var(--t);border-bottom-color:var(--purple)}
.tab-content{display:none}.tab-content.active{display:block}
.card{background:var(--s);border:1px solid var(--b);border-radius:10px;overflow:hidden;margin-bottom:16px}
table{width:100%;border-collapse:collapse}
th{font-size:11px;text-transform:uppercase;letter-spacing:.05em;color:var(--m);padding:10px 14px;text-align:left;border-bottom:1px solid var(--b);font-weight:500;white-space:nowrap}
td{padding:10px 14px;border-bottom:1px solid var(--b);font-size:13px}
tr:last-child td{border-bottom:none}
tr:hover td{background:var(--s2)}
.empty{padding:32px;text-align:center;color:var(--m)}
.log-box{background:#0a0c10;border:1px solid var(--b);border-radius:10px;padding:16px;font-family:monospace;font-size:12px;line-height:1.7;max-height:500px;overflow-y:auto;color:#a0aec0}
.log-info{color:#68d391}.log-warn{color:var(--amber)}.log-error{color:var(--red)}

/* Posiciones */
.pos-card{background:var(--s2);border:1px solid rgba(74,222,128,.2);border-left:3px solid var(--green);border-radius:10px;padding:16px 18px;margin-bottom:10px}
.pos-header{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:12px}
.pos-coin{font-size:18px;font-weight:600}
.pos-meta{font-size:12px;color:var(--m);line-height:1.8}
.pos-funding{font-size:16px;font-weight:600;color:var(--green);text-align:right}
.pos-stats{display:grid;grid-template-columns:repeat(4,1fr);gap:8px;padding-top:12px;border-top:1px solid var(--b)}
.pos-stat-label{font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.pos-stat-value{font-size:14px;font-weight:600}

/* Oportunidades */
.opp-card{background:var(--s);border:1px solid rgba(74,222,128,.2);border-left:3px solid var(--green);border-radius:10px;padding:14px 18px;margin-bottom:10px}
.opp-header{display:flex;justify-content:space-between;align-items:flex-start;flex-wrap:wrap;gap:8px;margin-bottom:10px}
.opp-coin{font-size:18px;font-weight:600}
.opp-badges{display:flex;gap:8px;flex-wrap:wrap;align-items:center}
.opp-legs{display:flex;align-items:center;gap:10px;flex-wrap:wrap;font-size:13px;margin-bottom:8px}
.opp-profits{display:grid;grid-template-columns:repeat(3,1fr);gap:8px;padding:10px;background:rgba(255,255,255,.03);border-radius:8px;margin-bottom:8px}
.opp-profit-label{font-size:10px;color:var(--m);text-transform:uppercase;letter-spacing:.05em;margin-bottom:3px}
.opp-profit-value{font-size:14px;font-weight:600;color:var(--green)}
.opp-note{font-size:11px;color:var(--m)}
.badge-cex{background:rgba(167,139,250,.15);color:#a78bfa;border:1px solid rgba(167,139,250,.3);border-radius:4px;padding:2px 7px;font-size:10px;font-weight:600}
.badge-dex{background:rgba(45,212,191,.12);color:var(--teal);border:1px solid rgba(45,212,191,.3);border-radius:4px;padding:2px 7px;font-size:10px;font-weight:600}
.badge-long{background:rgba(74,222,128,.1);color:#16a34a;border:1px solid rgba(74,222,128,.25);border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600}
.badge-short{background:rgba(248,113,113,.1);color:#dc2626;border:1px solid rgba(248,113,113,.25);border-radius:4px;padding:2px 7px;font-size:11px;font-weight:600}
.spread-badge{background:rgba(74,222,128,.12);color:#15803d;border:1px solid rgba(74,222,128,.3);border-radius:6px;padding:3px 10px;font-size:12px;font-weight:700;font-family:monospace}
.filter-row{display:flex;gap:8px;margin-bottom:14px;flex-wrap:wrap;align-items:center}
.filter-btn{padding:4px 12px;font-size:12px;border:1px solid var(--b);border-radius:6px;background:transparent;color:var(--m);cursor:pointer}
.filter-btn.active{background:rgba(74,222,128,.1);color:#16a34a;border-color:rgba(74,222,128,.3)}
.capital-input{display:flex;align-items:center;gap:8px;margin-left:auto}
.capital-input label{font-size:12px;color:var(--m)}
.capital-input input{width:100px;font-size:13px;background:var(--s2);border:1px solid var(--b);color:var(--t);border-radius:6px;padding:4px 8px}
.ex-strip{display:flex;flex-wrap:wrap;gap:8px;padding:10px 14px;background:var(--s);border-radius:8px;margin-bottom:14px;border:1px solid var(--b)}
.ex-item{display:flex;align-items:center;gap:5px;font-size:12px;color:var(--m)}
.ex-dot{width:7px;height:7px;border-radius:50%}
.ex-ok{background:var(--green)}.ex-err{background:var(--red)}.ex-load{background:var(--amber)}
.btn{background:var(--s2);border:1px solid var(--b);color:var(--t);padding:6px 14px;border-radius:8px;cursor:pointer;font-size:12px}
.btn:hover{background:var(--s)}
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

  <!-- Auth -->
  <div style="font-size:11px;font-weight:500;color:var(--m);text-transform:uppercase;letter-spacing:.05em;margin-bottom:10px">Estado de conexión</div>
  <div class="auth-grid" id="auth-grid">
    <div class="auth-card"><div style="color:var(--m);font-size:13px">Verificando...</div></div>
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
    <button class="tab" onclick="switchTab('opps');loadOpps()">Oportunidades</button>
    <button class="tab" onclick="switchTab('history')">Historial</button>
    <button class="tab" onclick="switchTab('logs')">Logs en vivo</button>
  </div>

  <!-- Posiciones -->
  <div id="tab-positions" class="tab-content active">
    <div id="positions-container"><div class="empty">Cargando...</div></div>
  </div>

  <!-- Oportunidades -->
  <div id="tab-opps" class="tab-content">
    <div class="filter-row">
      <button class="filter-btn active" onclick="setFilter('ALL',this)">Todos</button>
      <button class="filter-btn" onclick="setFilter('CEX',this)">CEX ↔ CEX</button>
      <button class="filter-btn" onclick="setFilter('DEX',this)">DEX ↔ DEX</button>
      <button class="filter-btn" onclick="setFilter('CEX-DEX',this)">CEX ↔ DEX</button>
      <div class="capital-input">
        <label>Monto (USDT):</label>
        <input type="number" id="opp-capital" value="500" min="100" step="100" oninput="renderOpps()">
      </div>
    </div>
    <div class="ex-strip" id="ex-strip">
      <span style="font-size:12px;color:var(--m)">Cargando exchanges...</span>
    </div>
    <div id="opps-list"><div class="empty">Cargando datos de exchanges...</div></div>
  </div>

  <!-- Historial -->
  <div id="tab-history" class="tab-content">
    <div class="card">
      <table>
        <thead><tr>
          <th>Par</th><th>Long en</th><th>Short en</th><th>Capital</th>
          <th>Spread</th><th>Modo</th><th>Apertura</th><th>Cierre</th>
          <th>Funding</th><th>PnL neto</th>
        </tr></thead>
        <tbody id="trades-body"><tr><td colspan="10" class="empty">Cargando...</td></tr></tbody>
      </table>
    </div>
  </div>

  <!-- Logs -->
  <div id="tab-logs" class="tab-content">
    <div class="log-box" id="log-box">Cargando logs...</div>
  </div>
</div>

<script>
// ── State ──────────────────────────────────────────────────────────────────
const COINS = ['BTC','ETH','SOL','BNB','ARB','DOGE','XRP','AVAX','OP','SUI','LINK','INJ','NEAR','TON'];
const EXCHANGES = [
  {id:'binance',    label:'Binance',     type:'CEX', h:8},
  {id:'bybit',      label:'Bybit',       type:'CEX', h:8},
  {id:'okx',        label:'OKX',         type:'CEX', h:8},
  {id:'bitget',     label:'Bitget',      type:'CEX', h:1},
  {id:'gate',       label:'Gate.io',     type:'CEX', h:8},
  {id:'mexc',       label:'MEXC',        type:'CEX', h:8},
  {id:'bingx',      label:'BingX',       type:'CEX', h:1},
  {id:'kucoin',     label:'KuCoin',      type:'CEX', h:8},
  {id:'hyperliquid',label:'HyperLiquid', type:'DEX', h:1},
  {id:'drift',      label:'Drift',       type:'DEX', h:1},
  {id:'dydx',       label:'dYdX',        type:'DEX', h:1},
];
const MIN_SPREAD = 0.003;
let rates={}, exStatus={}, filterType='ALL', oppsLoaded=false;

// ── Fetchers ──────────────────────────────────────────────────────────────
async function sf(url,opts){try{const r=await fetch(url,opts);if(!r.ok)throw new Error(r.status);return r.json()}catch{return null}}
const fetchers={
  binance:    async()=>{const d=await sf('https://fapi.binance.com/fapi/v1/premiumIndex');if(!d)return{};const o={};for(const x of d){const s=x.symbol.replace('USDT','').replace('PERP','');if(COINS.includes(s))o[s]={rate:parseFloat(x.lastFundingRate)*100,h:8};}return o;},
  bybit:      async()=>{const d=await sf('https://api.bybit.com/v5/market/tickers?category=linear');if(!d)return{};const o={};for(const x of d?.result?.list||[]){const s=x.symbol.replace('USDT','');if(COINS.includes(s)&&x.fundingRate)o[s]={rate:parseFloat(x.fundingRate)*100,h:8};}return o;},
  okx:        async()=>{const o={};await Promise.all(COINS.map(async c=>{const d=await sf(`https://www.okx.com/api/v5/public/funding-rate?instId=${c}-USDT-SWAP`);const x=d?.data?.[0];if(x)o[c]={rate:parseFloat(x.fundingRate)*100,h:8};}));return o;},
  bitget:     async()=>{const d=await sf('https://api.bitget.com/api/v2/mix/market/tickers?productType=USDT-FUTURES');if(!d)return{};const o={};for(const x of d?.data||[]){const s=x.symbol.replace('USDT','').replace('_UMCBL','');if(COINS.includes(s)&&x.fundingRate)o[s]={rate:parseFloat(x.fundingRate)*100,h:1};}return o;},
  gate:       async()=>{const o={};await Promise.all(COINS.map(async c=>{const d=await sf(`https://api.gateio.ws/api/v4/futures/usdt/contracts/${c}_USDT`);if(d?.funding_rate)o[c]={rate:parseFloat(d.funding_rate)*100,h:8};}));return o;},
  mexc:       async()=>{const o={};await Promise.all(COINS.map(async c=>{const d=await sf(`https://contract.mexc.com/api/v1/contract/funding_rate/${c}_USDT`);if(d?.data?.fundingRate)o[c]={rate:parseFloat(d.data.fundingRate)*100,h:8};}));return o;},
  bingx:      async()=>{const o={};await Promise.all(COINS.map(async c=>{const d=await sf(`https://open-api.bingx.com/openApi/swap/v2/quote/fundingRate?symbol=${c}-USDT`);if(d?.data?.fundingRate)o[c]={rate:parseFloat(d.data.fundingRate)*100,h:1};}));return o;},
  kucoin:     async()=>{const o={};await Promise.all(COINS.map(async c=>{const d=await sf(`https://api-futures.kucoin.com/api/v1/funding-rate/${c}USDTM/current`);if(d?.data?.value)o[c]={rate:parseFloat(d.data.value)*100,h:8};}));return o;},
  hyperliquid:async()=>{const d=await sf('https://api.hyperliquid.xyz/info',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({type:'metaAndAssetCtxs'})});if(!d)return{};const[meta,ctxs]=d;const o={};for(let i=0;i<meta.universe.length;i++){const n=meta.universe[i].name;if(COINS.includes(n))o[n]={rate:parseFloat(ctxs[i].funding)*100,h:1};}return o;},
  drift:      async()=>{const m={BTC:0,ETH:1,SOL:2};const o={};await Promise.all(Object.entries(m).map(async([c,idx])=>{const d=await sf(`https://data.api.drift.trade/fundingRates?marketIndex=${idx}&limit=1`);const r=d?.fundingRates?.[0];if(r){const p=(parseFloat(r.fundingRate)/1e9)/(parseFloat(r.oraclePriceTwap)/1e6)*100;o[c]={rate:p,h:1};}}));return o;},
  dydx:       async()=>{const o={};await Promise.all(COINS.map(async c=>{const d=await sf(`https://indexer.dydx.trade/v4/perpetualMarkets?ticker=${c}-USD`);const m=d?.markets?.[`${c}-USD`];if(m?.nextFundingRate)o[c]={rate:parseFloat(m.nextFundingRate)*100,h:1};}));return o;},
};

async function fetchAllRates(){
  await Promise.all(EXCHANGES.map(async ex=>{
    try{rates[ex.id]=await fetchers[ex.id]();exStatus[ex.id]='ok';}
    catch{rates[ex.id]={};exStatus[ex.id]='err';}
  }));
}

// ── Opp builder ───────────────────────────────────────────────────────────
function rph(rate,h){return rate/h}
function buildOpps(){
  const opps=[]; const seen=new Set();
  for(const coin of COINS){
    const exData=EXCHANGES.map(ex=>{
      const r=rates[ex.id]?.[coin];
      return r?{...ex,rateRaw:r.rate,h:r.h}:null;
    }).filter(Boolean);
    for(const lo of exData){
      for(const sh of exData){
        if(lo.id===sh.id)continue;
        if(filterType==='CEX'&&(lo.type!=='CEX'||sh.type!=='CEX'))continue;
        if(filterType==='DEX'&&(lo.type!=='DEX'||sh.type!=='DEX'))continue;
        if(filterType==='CEX-DEX'&&lo.type===sh.type)continue;
        const loH=rph(lo.rateRaw,lo.h), shH=rph(sh.rateRaw,sh.h);
        const spread=shH-loH;
        if(spread>MIN_SPREAD){
          const key=`${coin}-${lo.id}-${sh.id}`;
          if(!seen.has(key)){seen.add(key);opps.push({coin,lo,sh,spread,loH,shH});}
        }
      }
    }
  }
  return opps.sort((a,b)=>b.spread-a.spread);
}

function fmtR(r,d=4){if(r===null||r===undefined||isNaN(r))return'—';return(r>=0?'+':'')+r.toFixed(d)+'%'}
function fmtUSD(v){return(v>=0?'+$':'-$')+Math.abs(v).toFixed(2)}
function rateColor(r){
  if(r>0.015)return'#16a34a';if(r>0.003)return'#4ade80';if(r>0)return'#86efac';
  if(r<-0.015)return'#dc2626';if(r<-0.003)return'#f87171';return'#fca5a5';
}

function renderExStrip(){
  const ok=Object.values(exStatus).filter(s=>s==='ok').length;
  document.getElementById('ex-strip').innerHTML=
    EXCHANGES.map(ex=>{
      const s=exStatus[ex.id];
      const cls=s==='ok'?'ex-ok':s==='err'?'ex-err':'ex-load';
      const tc=ex.type==='CEX'?'badge-cex':'badge-dex';
      return`<div class="ex-item"><span class="ex-dot ${cls}"></span>${ex.label}<span class="${tc}">${ex.type}</span></div>`;
    }).join('')+`<span style="margin-left:auto;font-size:11px;color:var(--m)">${ok}/${EXCHANGES.length} activos</span>`;
}

function renderOpps(){
  const capital=parseFloat(document.getElementById('opp-capital')?.value)||500;
  const opps=buildOpps();
  const cont=document.getElementById('opps-list');
  if(!opps.length){
    cont.innerHTML='<div class="empty">Sin oportunidades con spread > '+MIN_SPREAD.toFixed(3)+'%/h ahora mismo</div>';
    return;
  }
  cont.innerHTML=opps.slice(0,20).map(o=>{
    const dailyUSD=capital*(o.spread/100)*24;
    const monthlyUSD=dailyUSD*30;
    const fees=capital*0.002;
    const pnlNet=monthlyUSD-fees;
    const loTypeCls=o.lo.type==='CEX'?'badge-cex':'badge-dex';
    const shTypeCls=o.sh.type==='CEX'?'badge-cex':'badge-dex';
    return`<div class="opp-card">
      <div class="opp-header">
        <div style="display:flex;align-items:center;gap:10px">
          <span class="opp-coin">${o.coin}</span>
          <span style="font-size:12px;color:var(--m)">PERP</span>
        </div>
        <div class="opp-badges">
          <span class="spread-badge">+${o.spread.toFixed(4)}%/h spread</span>
          <span style="font-size:12px;color:var(--m);font-family:monospace">~${fmtUSD(monthlyUSD)}/mes</span>
          <span style="font-size:11px;color:var(--m)">con $${capital.toLocaleString()}</span>
        </div>
      </div>
      <div class="opp-legs">
        <span class="badge-long">LARGO</span>
        <strong>${o.lo.label}</strong>
        <span class="${loTypeCls}">${o.lo.type}</span>
        <span style="color:${rateColor(o.loH)};font-family:monospace;font-size:12px">${fmtR(o.lo.rateRaw)} / ${o.lo.h}h</span>
        <span style="color:var(--m)">→</span>
        <span class="badge-short">CORTO</span>
        <strong>${o.sh.label}</strong>
        <span class="${shTypeCls}">${o.sh.type}</span>
        <span style="color:${rateColor(o.shH)};font-family:monospace;font-size:12px">${fmtR(o.sh.rateRaw)} / ${o.sh.h}h</span>
      </div>
      <div class="opp-profits">
        <div><div class="opp-profit-label">Ganancia/día</div><div class="opp-profit-value">${fmtUSD(dailyUSD)}</div></div>
        <div><div class="opp-profit-label">Ganancia/mes</div><div class="opp-profit-value">${fmtUSD(monthlyUSD)}</div></div>
        <div><div class="opp-profit-label">PnL neto est.</div><div class="opp-profit-value" style="color:${pnlNet>=0?'var(--green)':'var(--red)'}">${fmtUSD(pnlNet)}</div></div>
      </div>
      <div class="opp-note">Fees est. 0.2% (entrada+salida): -$${fees.toFixed(2)} · Tasas normalizadas a /hora para comparación justa</div>
    </div>`;
  }).join('');
}

async function loadOpps(){
  if(oppsLoaded)return;
  document.getElementById('opps-list').innerHTML='<div class="empty">Consultando 11 exchanges...</div>';
  await fetchAllRates();
  renderExStrip();
  renderOpps();
  oppsLoaded=true;
  setInterval(async()=>{await fetchAllRates();renderExStrip();renderOpps();},45000);
}

function setFilter(f,btn){
  filterType=f;
  document.querySelectorAll('.filter-btn').forEach(b=>b.classList.remove('active'));
  btn.classList.add('active');
  renderOpps();
}

// ── Dashboard data ────────────────────────────────────────────────────────
async function fetchJson(url){try{const r=await fetch(url);return r.json()}catch{return null}}
function fmt(v,d=4){if(v===null||v===undefined)return'—';const n=parseFloat(v);return(n>=0?'+':'')+n.toFixed(d)}
function fmtDate(iso){if(!iso)return'—';return new Date(iso).toLocaleString('es-AR',{day:'2-digit',month:'2-digit',hour:'2-digit',minute:'2-digit'})}

async function loadAuth(){
  const d=await fetchJson('/api/auth');
  if(!d)return;
  const exs=['bybit','okx','bitget'];
  const labels={bybit:'Bybit',okx:'OKX',bitget:'Bitget'};
  document.getElementById('auth-grid').innerHTML=exs.map(ex=>{
    const info=d[ex];
    if(!info)return`<div class="auth-card"><div class="auth-name">${labels[ex]}</div><div style="color:var(--m);font-size:13px;margin-top:8px">Sin datos</div></div>`;
    let dotCls,statusText,statusColor;
    if(info.status==='ok'){dotCls='auth-dot-ok';statusText='Conectado';statusColor='var(--green)';}
    else if(info.status==='error'){dotCls='auth-dot-err';statusText='Error';statusColor='var(--red)';}
    else{dotCls='auth-dot-nokey';statusText='Sin key';statusColor='var(--m)';}
    const modeBadge=info.status!=='no_key'?(info.demo?`<span class="badge badge-demo" style="font-size:10px">DEMO</span>`:`<span class="badge badge-real" style="font-size:10px">REAL</span>`):'';
    let body='';
    if(info.status==='ok'){
      body=info.free!==null
        ?`<div class="auth-row"><span class="auth-label">Libre</span><span class="green">$${info.free?.toLocaleString()} USDT</span></div>
           <div class="auth-row"><span class="auth-label">Total</span><span>$${info.total?.toLocaleString()} USDT</span></div>`
        :`<div class="auth-row"><span class="auth-label">Balance</span><span style="color:var(--m);font-size:11px">${info.note||'No disponible en demo'}</span></div>`;
      body+=`<div class="auth-row"><span class="auth-label">Modo</span><span>${modeBadge}</span></div>`;
      body+=`<div class="auth-row"><span class="auth-label">Verificado</span><span style="color:var(--m);font-size:11px">${fmtDate(d.checked_at)}</span></div>`;
    }else if(info.status==='error'){
      body=`<div class="auth-row"><span class="auth-label">Modo</span><span>${modeBadge}</span></div>
            <div class="auth-error">⚠ ${info.error||'Error desconocido'}</div>`;
    }else{
      body=`<div style="font-size:12px;color:var(--m);margin-top:8px">Cargá las API keys en Railway Variables para activar este exchange.</div>`;
    }
    return`<div class="auth-card">
      <div class="auth-card-header">
        <div class="auth-name">${labels[ex]}</div>
        <div class="auth-status"><span class="auth-dot ${dotCls}"></span><span style="color:${statusColor}">${statusText}</span></div>
      </div>${body}</div>`;
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
    const dailyEst=p.capital*(p.entry_rate/100)*24;
    const monthlyEst=dailyEst*30;
    const modeBadge=p.mode==='demo'?`<span class="badge badge-demo" style="font-size:10px">DEMO</span>`:
                    p.mode==='real'?`<span class="badge badge-real" style="font-size:10px">REAL</span>`:
                    `<span class="badge badge-paper" style="font-size:10px">PAPER</span>`;
    const cycles=p.funding_cycles||0;
    return`<div class="pos-card">
      <div class="pos-header">
        <div>
          <div class="pos-coin">${p.spot_symbol||p.symbol}</div>
          <div style="font-size:11px;color:var(--purple);margin-top:3px;font-weight:500">Spread inter-exchange</div>
          <div style="margin-top:5px">${modeBadge}</div>
        </div>
        <div>
          <div style="font-size:11px;color:var(--m);margin-bottom:4px;text-align:right">Funding acumulado</div>
          <div class="pos-funding">+$${parseFloat(p.funding_collected||0).toFixed(4)}</div>
          <div style="font-size:11px;color:var(--m);text-align:right;margin-top:3px">${cycles} ciclo${cycles!==1?'s':''}</div>
        </div>
      </div>
      <div class="pos-meta">
        Long: <strong style="color:var(--t)">${p.long_exchange}</strong> &nbsp;·&nbsp;
        Short: <strong style="color:var(--t)">${p.short_exchange}</strong><br>
        Capital: $${p.capital} &nbsp;·&nbsp; Rate entrada: ${parseFloat(p.entry_rate||0).toFixed(4)}% &nbsp;·&nbsp;
        Abierta: ${fmtDate(p.opened_at)}
      </div>
      <div class="pos-stats">
        <div><div class="pos-stat-label">Rate/spread</div><div class="pos-stat-value" style="color:var(--green)">${parseFloat(p.entry_rate||0).toFixed(4)}%</div></div>
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
  if(!trades?.length){tbody.innerHTML='<tr><td colspan="10" class="empty">Sin trades cerrados aún</td></tr>';return;}
  tbody.innerHTML=trades.map(t=>{
    const pnl=parseFloat(t.pnl_net||0);
    const modeBadge=t.mode==='demo'?`<span class="badge badge-demo" style="font-size:10px">DEMO</span>`:
                    t.mode==='real'?`<span class="badge badge-real" style="font-size:10px">REAL</span>`:
                    `<span class="badge badge-paper" style="font-size:10px">PAPER</span>`;
    return`<tr>
      <td><strong>${t.symbol}</strong></td>
      <td>${t.long_exchange||'—'}</td><td>${t.short_exchange||'—'}</td>
      <td>$${t.capital}</td>
      <td style="font-family:monospace">${parseFloat(t.rate_at_open||0).toFixed(4)}%</td>
      <td>${modeBadge}</td>
      <td>${fmtDate(t.opened_at)}</td><td>${fmtDate(t.closed_at)}</td>
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
    t.classList.toggle('active',['positions','opps','history','logs'][i]===name);
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
setInterval(()=>{if(document.querySelector('.tab.active')?.textContent.includes('Logs'))loadLogs();},10000);
</script>
</body>
</html>"""

@app.route("/")
def index():
    return render_template_string(HTML)

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port, debug=False)

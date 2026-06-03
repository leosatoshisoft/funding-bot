"""
Funding Rate Arbitrage Bot
- Rates: clientes publicos sin key (sin bloqueos de demo)
- Ordenes: clientes autenticados demo/real
"""

import os
import time
import json
import logging
from datetime import datetime, timezone
from typing import Optional
import ccxt

os.makedirs("logs", exist_ok=True)
os.makedirs("data", exist_ok=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler("logs/bot.log"),
    ],
)
log = logging.getLogger(__name__)


# ─── Config ──────────────────────────────────────────────────────────────────
class Config:
    BYBIT_API_KEY      = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET   = os.getenv("BYBIT_API_SECRET", "")
    BYBIT_DEMO         = os.getenv("BYBIT_DEMO", "true").lower() == "true"

    BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

    BITGET_API_KEY     = os.getenv("BITGET_API_KEY", "")
    BITGET_API_SECRET  = os.getenv("BITGET_API_SECRET", "")
    BITGET_PASSPHRASE  = os.getenv("BITGET_PASSPHRASE", "")
    BITGET_DEMO        = os.getenv("BITGET_DEMO", "true").lower() == "true"

    OKX_API_KEY        = os.getenv("OKX_API_KEY", "")
    OKX_API_SECRET     = os.getenv("OKX_API_SECRET", "")
    OKX_PASSPHRASE     = os.getenv("OKX_PASSPHRASE", "")
    OKX_DEMO           = os.getenv("OKX_DEMO", "true").lower() == "true"

    PAPER_TRADING      = os.getenv("PAPER_TRADING", "true").lower() == "true"
    MIN_SPREAD         = float(os.getenv("MIN_SPREAD", "0.003"))
    CAPITAL_PER_TRADE  = float(os.getenv("CAPITAL_PER_TRADE", "500"))
    MAX_POSITIONS      = int(os.getenv("MAX_POSITIONS", "4"))
    CHECK_INTERVAL     = int(os.getenv("CHECK_INTERVAL", "3600"))
    FUNDING_INTERVAL_H = int(os.getenv("FUNDING_INTERVAL_H", "8"))

    SYMBOLS = [
        "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
        "BNB/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT",
        "AVAX/USDT:USDT", "LINK/USDT:USDT", "OP/USDT:USDT",
        "ARB/USDT:USDT", "SUI/USDT:USDT", "TON/USDT:USDT",
        "INJ/USDT:USDT", "NEAR/USDT:USDT",
    ]

    @staticmethod
    def spot_symbol(sym):
        return sym.split(":")[0]


# ─── Exchange clients ─────────────────────────────────────────────────────────
def init_exchanges():
    """
    Devuelve dos dicts:
    - rate_clients: sin autenticacion, para consultar funding rates publicos
    - trade_clients: autenticados demo/real, para ejecutar ordenes
    """
    rate_clients  = {}
    trade_clients = {}

    # ── Bybit ─────────────────────────────────────────────────────────────────
    # Rates: cliente publico (endpoint real, sin key)
    rate_clients["bybit"] = ccxt.bybit({
        "enableRateLimit": True,
        "options": {"defaultType": "linear"},
    })
    # Ordenes: cliente demo con endpoint correcto
    if Config.BYBIT_API_KEY:
        bybit_trade = {
            "apiKey": Config.BYBIT_API_KEY,
            "secret": Config.BYBIT_API_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "linear"},
        }
        if Config.BYBIT_DEMO:
            # Endpoint demo correcto de Bybit
            bybit_trade["urls"] = {
                "api": {
                    "public":  "https://api-demo.bybit.com",
                    "private": "https://api-demo.bybit.com",
                }
            }
        trade_clients["bybit"] = ccxt.bybit(bybit_trade)
        # Cliente spot para compras
        bybit_spot = dict(bybit_trade)
        bybit_spot["options"] = {"defaultType": "spot"}
        trade_clients["bybit_spot"] = ccxt.bybit(bybit_spot)
    log.info(f"Bybit rates: publico | trade: {'demo' if Config.BYBIT_DEMO else 'real' if Config.BYBIT_API_KEY else 'sin key'}")

    # ── Binance ────────────────────────────────────────────────────────────────
    rate_clients["binance"] = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })
    log.info("Binance: solo rates publicos")

    # ── Bitget ────────────────────────────────────────────────────────────────
    rate_clients["bitget"] = ccxt.bitget({
        "enableRateLimit": True,
        "options": {"defaultType": "swap"},
    })
    if Config.BITGET_API_KEY:
        bitget_trade = {
            "apiKey":   Config.BITGET_API_KEY,
            "secret":   Config.BITGET_API_SECRET,
            "password": Config.BITGET_PASSPHRASE,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if Config.BITGET_DEMO:
            bitget_trade["urls"] = {"api": "https://api-sandbox.bitget.com"}
        trade_clients["bitget"] = ccxt.bitget(bitget_trade)
    log.info(f"Bitget rates: publico | trade: {'demo' if Config.BITGET_DEMO else 'real' if Config.BITGET_API_KEY else 'sin key'}")

    # ── OKX ────────────────────────────────────────────────────────────────────
    # Rates: SIEMPRE publico sin key (demo bloquea fetch_funding_rate)
    rate_clients["okx"] = ccxt.okx({
        "enableRateLimit": True,
        "options": {"defaultType": "swap"},
    })
    if Config.OKX_API_KEY:
        okx_trade = {
            "apiKey":   Config.OKX_API_KEY,
            "secret":   Config.OKX_API_SECRET,
            "password": Config.OKX_PASSPHRASE,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if Config.OKX_DEMO:
            okx_trade["headers"] = {"x-simulated-trading": "1"}
        trade_clients["okx"] = ccxt.okx(okx_trade)
    log.info(f"OKX rates: publico | trade: {'demo' if Config.OKX_DEMO else 'real' if Config.OKX_API_KEY else 'sin key'}")

    return rate_clients, trade_clients


# ─── Auth checker ─────────────────────────────────────────────────────────────
DEMO_CODES = ["50038", "40099", "unavailable", "environment", "demo", "paper", "simulated"]

def _is_demo_limit(err):
    return any(c in err.lower() for c in DEMO_CODES)

def check_auth(trade_clients):
    cfg = {
        "bybit":  (Config.BYBIT_API_KEY,  Config.BYBIT_DEMO),
        "okx":    (Config.OKX_API_KEY,    Config.OKX_DEMO),
        "bitget": (Config.BITGET_API_KEY, Config.BITGET_DEMO),
    }
    results = {}
    for name, (key, is_demo) in cfg.items():
        if not key:
            results[name] = {"status": "no_key", "free": None, "total": None,
                             "error": None, "demo": is_demo, "note": None}
            continue
        client = trade_clients.get(name)
        if not client:
            results[name] = {"status": "no_key", "free": None, "total": None,
                             "error": None, "demo": is_demo, "note": None}
            continue
        try:
            balance = client.fetch_balance()
            usdt  = balance.get("USDT", {})
            free  = float(usdt.get("free",  0))
            total = float(usdt.get("total", 0))
            results[name] = {"status": "ok", "free": round(free, 2),
                             "total": round(total, 2), "error": None,
                             "demo": is_demo, "note": None}
            log.info(f"[{name}] Auth OK | USDT: ${free:.2f} libre / ${total:.2f} total")
        except Exception as e:
            err = str(e)
            if is_demo and _is_demo_limit(err):
                results[name] = {"status": "ok", "free": None, "total": None,
                                 "error": None, "demo": True,
                                 "note": "Cuenta demo activa"}
                log.info(f"[{name}] Auth OK (demo)")
            else:
                results[name] = {"status": "error", "free": None, "total": None,
                                 "error": err[:150], "demo": is_demo, "note": None}
                log.error(f"[{name}] Auth FAILED: {err[:80]}")
    return results


def save_auth_status(status):
    with open("data/auth_status.json", "w") as f:
        json.dump({**status, "checked_at": datetime.utcnow().isoformat()}, f, indent=2)


# ─── Funding rate fetcher (usa rate_clients — publicos) ───────────────────────
def fetch_rates_from(name, client):
    rates = {}
    for symbol in Config.SYMBOLS:
        try:
            data = client.fetch_funding_rate(symbol)
            rate = data.get("fundingRate")
            if rate is not None:
                rates[symbol] = float(rate) * 100
        except Exception as e:
            log.debug(f"[{name}] {symbol}: {str(e)[:80]}")
    return rates


def get_all_rates(rate_clients):
    raw = {}
    log.info(f"Consultando rates de: {list(rate_clients.keys())}")
    for name, client in rate_clients.items():
        r = fetch_rates_from(name, client)
        log.info(f"[{name}] {len(r)} rates obtenidos")
        if not r:
            log.warning(f"[{name}] SIN RATES")
        for sym, rate in r.items():
            raw.setdefault(sym, {})[name] = rate

    result = {}
    for sym, ex_rates in raw.items():
        if not ex_rates:
            continue
        best_ex   = max(ex_rates, key=ex_rates.get)
        best_rate = ex_rates[best_ex]
        best_spread = 0.0
        spread_long = spread_short = None
        items = list(ex_rates.items())
        for i, (ex_a, rate_a) in enumerate(items):
            for ex_b, rate_b in items[i+1:]:
                if rate_b > rate_a:
                    sp, lo, sh = rate_b - rate_a, ex_a, ex_b
                else:
                    sp, lo, sh = rate_a - rate_b, ex_b, ex_a
                if sp > best_spread:
                    best_spread, spread_long, spread_short = sp, lo, sh
        result[sym] = {
            "rates":         ex_rates,
            "best_rate":     best_rate,
            "best_exchange": best_ex,
            "best_spread":   round(best_spread, 6),
            "spread_long":   spread_long,
            "spread_short":  spread_short,
        }
    return result


# ─── Helpers ──────────────────────────────────────────────────────────────────
def can_trade(exchange, trade_clients):
    return exchange in trade_clients

def hours_since(iso):
    dt  = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 3600


# ─── Position manager ─────────────────────────────────────────────────────────
class PositionManager:
    def __init__(self):
        self.positions = self._load()

    def _load(self):
        try:
            with open("data/positions.json") as f:
                return json.load(f)
        except:
            return []

    def _save(self):
        with open("data/positions.json", "w") as f:
            json.dump(self.positions, f, indent=2)

    def add(self, pos):
        self.positions.append(pos)
        self._save()

    def remove(self, uid):
        self.positions = [p for p in self.positions if p["id"] != uid]
        self._save()

    def get_by_symbol(self, symbol):
        return [p for p in self.positions if p["symbol"] == symbol]

    def count(self):
        return len(self.positions)

    def update_funding(self, uid, earned):
        for p in self.positions:
            if p["id"] == uid:
                p["funding_collected"] = round(p.get("funding_collected", 0) + earned, 6)
                p["funding_cycles"]    = p.get("funding_cycles", 0) + 1
                p["last_funding_at"]   = datetime.utcnow().isoformat()
                self._save()
                break


# ─── Trade logger ─────────────────────────────────────────────────────────────
class TradeLogger:
    def __init__(self):
        self.path   = "data/trades.json"
        self.trades = self._load()

    def _load(self):
        try:
            with open(self.path) as f:
                return json.load(f)
        except:
            return []

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.trades, f, indent=2)

    def log_open(self, uid, symbol, capital, strategy, rate, long_ex, short_ex, mode):
        self.trades.append({
            "id": uid, "symbol": symbol, "capital": capital,
            "strategy": strategy, "rate_at_open": rate,
            "long_exchange": long_ex, "short_exchange": short_ex,
            "opened_at": datetime.utcnow().isoformat(),
            "closed_at": None, "funding_collected": 0,
            "pnl_net": None, "status": "open", "mode": mode,
        })
        self._save()

    def log_close(self, uid, funding, pnl):
        for t in self.trades:
            if t["id"] == uid and t["status"] == "open":
                t["closed_at"]         = datetime.utcnow().isoformat()
                t["funding_collected"] = round(funding, 6)
                t["pnl_net"]           = round(pnl, 6)
                t["status"]            = "closed"
                break
        self._save()

    def sync_open_funding(self, positions):
        pos_map = {p["id"]: p for p in positions}
        for t in self.trades:
            if t["status"] == "open" and t["id"] in pos_map:
                t["funding_collected"] = pos_map[t["id"]].get("funding_collected", 0)
        self._save()

    def summary(self):
        closed  = [t for t in self.trades if t.get("status") == "closed"]
        open_t  = [t for t in self.trades if t.get("status") == "open"]
        pnl     = sum(t.get("pnl_net") or 0 for t in closed)
        fund_cl = sum(t.get("funding_collected", 0) for t in closed)
        fund_op = sum(t.get("funding_collected", 0) for t in open_t)
        win     = [t for t in closed if (t.get("pnl_net") or 0) > 0]
        return {
            "total_trades":   len(closed),
            "total_pnl":      round(pnl, 4),
            "total_funding":  round(fund_cl + fund_op, 4),
            "open_positions": len(open_t),
            "win_rate":       round(len(win) / len(closed) * 100, 1) if closed else 0,
            "spread_trades":  len([t for t in closed if t.get("strategy") == "spread"]),
        }


# ─── Core bot ─────────────────────────────────────────────────────────────────
class FundingBot:
    def __init__(self):
        self.rate_clients, self.trade_clients = init_exchanges()
        self.pm = PositionManager()
        self.tl = TradeLogger()

        log.info("Verificando autenticacion...")
        auth = check_auth(self.trade_clients)
        save_auth_status(auth)

        tradeable = list(self.trade_clients.keys())
        log.info(f"Trade clients activos: {tradeable}")
        log.info(f"PAPER_TRADING: {Config.PAPER_TRADING}")
        log.info(f"Capital/trade: ${Config.CAPITAL_PER_TRADE} | Spread min: {Config.MIN_SPREAD}% | Max pos: {Config.MAX_POSITIONS}")

    def _uid(self, symbol, strategy):
        return f"{symbol}_{strategy}_{int(time.time())}"

    def _position_mode(self, long_ex, short_ex):
        if Config.PAPER_TRADING:
            return "paper"
        modes = {
            "bybit":   "demo" if Config.BYBIT_DEMO  else "real",
            "binance": "real",
            "bitget":  "demo" if Config.BITGET_DEMO else "real",
            "okx":     "demo" if Config.OKX_DEMO    else "real",
        }
        ml = modes.get(long_ex,  "real")
        ms = modes.get(short_ex, "real")
        return ml if ml == ms else f"{ml}/{ms}"

    def open_spread(self, symbol, spread, long_ex, short_ex):
        if self.pm.get_by_symbol(symbol) or self.pm.count() >= Config.MAX_POSITIONS:
            return

        if not Config.PAPER_TRADING:
            if not can_trade(long_ex, self.trade_clients) or \
               not can_trade(short_ex, self.trade_clients):
                log.warning(f"[spread] Skip {symbol}: {long_ex}/{short_ex} sin trade client")
                return

        uid  = self._uid(symbol, "spread")
        mode = self._position_mode(long_ex, short_ex)

        try:
            # Precio via cliente de rates (publico, siempre disponible)
            ref    = self.rate_clients.get(long_ex, list(self.rate_clients.values())[0])
            ticker = ref.fetch_ticker(Config.spot_symbol(symbol))
            price  = float(ticker["last"])
            amount = Config.CAPITAL_PER_TRADE / price

            if Config.PAPER_TRADING:
                log.info(f"[PAPER] LONG  {symbol} → {long_ex}")
                log.info(f"[PAPER] SHORT {symbol} → {short_ex} | Spread: {spread:.4f}%")
            else:
                self.trade_clients[long_ex].create_market_buy_order(symbol, amount)
                self.trade_clients[short_ex].create_market_sell_order(symbol, amount)
                log.info(f"[{mode.upper()}] LONG {long_ex} / SHORT {short_ex} ejecutado")

            pos = {
                "id": uid, "symbol": symbol,
                "spot_symbol": Config.spot_symbol(symbol),
                "capital": Config.CAPITAL_PER_TRADE, "amount": amount,
                "entry_price": price, "entry_rate": spread,
                "strategy": "spread",
                "long_exchange": long_ex, "short_exchange": short_ex,
                "opened_at": datetime.utcnow().isoformat(),
                "funding_collected": 0, "funding_cycles": 0,
                "last_funding_at": None, "mode": mode,
            }
            self.pm.add(pos)
            self.tl.log_open(uid, symbol, Config.CAPITAL_PER_TRADE,
                             "spread", spread, long_ex, short_ex, mode)
            log.info(f"Abierto: {symbol} | Spread: {spread:.4f}% | {long_ex}→{short_ex} | {mode}")

        except Exception as e:
            log.error(f"Error abriendo {symbol}: {e}")

    def close_position(self, pos, reason="manual"):
        try:
            if not Config.PAPER_TRADING:
                self.trade_clients[pos["long_exchange"]].create_market_sell_order(
                    pos["symbol"], pos["amount"])
                self.trade_clients[pos["short_exchange"]].create_market_buy_order(
                    pos["symbol"], pos["amount"])
            fees = Config.CAPITAL_PER_TRADE * 0.002
            pnl  = pos["funding_collected"] - fees
            self.tl.log_close(pos["id"], pos["funding_collected"], pnl)
            self.pm.remove(pos["id"])
            log.info(f"Cerrado: {pos['symbol']} | Funding: ${pos['funding_collected']:.4f} | PnL: ${pnl:.4f} | {reason}")
        except Exception as e:
            log.error(f"Error cerrando {pos['symbol']}: {e}")

    def _should_collect(self, pos):
        last = pos.get("last_funding_at")
        if not last:
            return True
        return hours_since(last) >= Config.FUNDING_INTERVAL_H

    def run_cycle(self):
        log.info("=" * 70)
        log.info("Iniciando ciclo...")

        auth = check_auth(self.trade_clients)
        save_auth_status(auth)

        all_rates = get_all_rates(self.rate_clients)
        if not all_rates:
            log.warning("SIN RATES de ningun exchange")
            return

        rate_exs = list(self.rate_clients.keys())
        log.info(f"{'Par':<18}" + "".join(f"{e:>10}" for e in rate_exs) + "   Spread  Estado")
        log.info("-" * 80)

        spread_opps = []

        for sym in Config.SYMBOLS:
            data = all_rates.get(sym)
            if not data:
                continue
            rates_str   = "".join(f"{data['rates'].get(e, 0):>9.4f}%" for e in rate_exs)
            best_spread = data["best_spread"]
            has_pos     = bool(self.pm.get_by_symbol(sym))

            if has_pos:
                status = "ABIERTA"
            elif best_spread >= Config.MIN_SPREAD:
                lo, sh = data["spread_long"], data["spread_short"]
                # Verificar que ambos exchanges tengan trade client
                if Config.PAPER_TRADING or \
                   (can_trade(lo, self.trade_clients) and can_trade(sh, self.trade_clients)):
                    status = f"SPREAD {lo}→{sh}"
                else:
                    status = f"sin key ({lo}/{sh})"
            else:
                status = "—"

            log.info(f"{sym:<18}{rates_str}  {best_spread:>7.4f}%  {status}")

            if not has_pos and best_spread >= Config.MIN_SPREAD:
                lo, sh = data["spread_long"], data["spread_short"]
                if Config.PAPER_TRADING or \
                   (can_trade(lo, self.trade_clients) and can_trade(sh, self.trade_clients)):
                    spread_opps.append((sym, best_spread, lo, sh))

        # Actualizar funding
        for pos in list(self.pm.positions):
            data = all_rates.get(pos["symbol"])
            if not data:
                continue
            long_rate  = data["rates"].get(pos["long_exchange"],  0)
            short_rate = data["rates"].get(pos["short_exchange"], 0)
            spread     = short_rate - long_rate
            if spread > 0 and self._should_collect(pos):
                earned = pos["capital"] * (spread / 100)
                self.pm.update_funding(pos["id"], earned)
                log.info(f"Funding {pos['symbol']}: +${earned:.4f} (spread {spread:.4f}%)")
            elif spread < -0.005:
                self.close_position(pos, "spread_invertido")

        self.tl.sync_open_funding(self.pm.positions)

        spread_opps.sort(key=lambda x: x[1], reverse=True)
        for sym, spread, lo, sh in spread_opps:
            if self.pm.count() < Config.MAX_POSITIONS:
                self.open_spread(sym, spread, lo, sh)

        summary = self.tl.summary()
        log.info("─" * 70)
        log.info(
            f"RESUMEN | Abiertas: {self.pm.count()} | "
            f"Cerradas: {summary['total_trades']} | "
            f"Funding: ${summary['total_funding']} | "
            f"PnL: ${summary['total_pnl']}"
        )

    def run(self):
        log.info("=" * 70)
        log.info("  FUNDING RATE BOT — Spread inter-exchange")
        log.info(f"  Modo: {'PAPER' if Config.PAPER_TRADING else 'DEMO/REAL'}")
        log.info("=" * 70)
        while True:
            try:
                self.run_cycle()
            except KeyboardInterrupt:
                log.info("Bot detenido.")
                break
            except Exception as e:
                log.error(f"Error en ciclo: {e}")
            log.info(f"Proximo ciclo en {Config.CHECK_INTERVAL // 60} minutos...")
            time.sleep(Config.CHECK_INTERVAL)


if __name__ == "__main__":
    FundingBot().run()

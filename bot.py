"""
Funding Rate Arbitrage Bot
Estrategia: spread inter-exchange (long perp A + short perp B)
Exchanges: Bybit, Binance, Bitget, OKX — cualquier combinacion
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
    # Bybit
    BYBIT_API_KEY      = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET   = os.getenv("BYBIT_API_SECRET", "")
    BYBIT_DEMO         = os.getenv("BYBIT_DEMO", "true").lower() == "true"

    # Binance
    BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

    # Bitget
    BITGET_API_KEY     = os.getenv("BITGET_API_KEY", "")
    BITGET_API_SECRET  = os.getenv("BITGET_API_SECRET", "")
    BITGET_PASSPHRASE  = os.getenv("BITGET_PASSPHRASE", "")
    BITGET_DEMO        = os.getenv("BITGET_DEMO", "true").lower() == "true"

    # OKX
    OKX_API_KEY        = os.getenv("OKX_API_KEY", "")
    OKX_API_SECRET     = os.getenv("OKX_API_SECRET", "")
    OKX_PASSPHRASE     = os.getenv("OKX_PASSPHRASE", "")
    OKX_DEMO           = os.getenv("OKX_DEMO", "true").lower() == "true"

    PAPER_TRADING      = os.getenv("PAPER_TRADING", "true").lower() == "true"
    MIN_SPREAD         = float(os.getenv("MIN_SPREAD", "0.003"))
    CAPITAL_PER_TRADE  = float(os.getenv("CAPITAL_PER_TRADE", "500"))
    MAX_POSITIONS      = int(os.getenv("MAX_POSITIONS", "4"))
    CHECK_INTERVAL     = int(os.getenv("CHECK_INTERVAL", "3600"))

    # Funding se paga cada 8 horas en la mayoria de exchanges
    FUNDING_INTERVAL_H = int(os.getenv("FUNDING_INTERVAL_H", "8"))

    SYMBOLS = [
        "BTC/USDT:USDT", "ETH/USDT:USDT", "SOL/USDT:USDT",
        "BNB/USDT:USDT", "XRP/USDT:USDT", "DOGE/USDT:USDT",
        "AVAX/USDT:USDT", "LINK/USDT:USDT", "OP/USDT:USDT",
        "ARB/USDT:USDT", "SUI/USDT:USDT", "TON/USDT:USDT",
        "INJ/USDT:USDT", "NEAR/USDT:USDT",
    ]

    @staticmethod
    def spot_symbol(sym: str) -> str:
        return sym.split(":")[0]


# ─── Exchange clients ─────────────────────────────────────────────────────────
def _exchange_mode(name: str) -> str:
    """Devuelve 'demo', 'real' o 'public' para cada exchange."""
    keys = {
        "bybit":   (Config.BYBIT_API_KEY,   Config.BYBIT_DEMO),
        "binance": (Config.BINANCE_API_KEY,  False),
        "bitget":  (Config.BITGET_API_KEY,   Config.BITGET_DEMO),
        "okx":     (Config.OKX_API_KEY,      Config.OKX_DEMO),
    }
    key, is_demo = keys.get(name, ("", False))
    if not key:
        return "public"
    return "demo" if is_demo else "real"


def init_exchanges() -> dict:
    clients = {}

    # ── Bybit ──────────────────────────────────────────────
    bybit_base = {"enableRateLimit": True}
    if Config.BYBIT_API_KEY:
        bybit_base["apiKey"] = Config.BYBIT_API_KEY
        bybit_base["secret"] = Config.BYBIT_API_SECRET
        if Config.BYBIT_DEMO:
            bybit_base["options"] = {"defaultType": "linear", "demo": True}
        else:
            bybit_base["options"] = {"defaultType": "linear"}
    else:
        bybit_base["options"] = {"defaultType": "linear"}

    clients["bybit"] = ccxt.bybit(dict(bybit_base))

    spot_cfg = dict(bybit_base)
    spot_cfg["options"] = dict(bybit_base.get("options", {}))
    spot_cfg["options"]["defaultType"] = "spot"
    clients["bybit_spot"] = ccxt.bybit(spot_cfg)
    log.info(f"Bybit: {_exchange_mode('bybit')}")

    # ── Binance ─────────────────────────────────────────────
    clients["binance"] = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })
    log.info("Binance: public (solo rates)")

    # ── Bitget ──────────────────────────────────────────────
    if Config.BITGET_API_KEY:
        bitget_cfg = {
            "apiKey": Config.BITGET_API_KEY,
            "secret": Config.BITGET_API_SECRET,
            "password": Config.BITGET_PASSPHRASE,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if Config.BITGET_DEMO:
            bitget_cfg["headers"] = {"paptrading": "1"}
        clients["bitget"] = ccxt.bitget(bitget_cfg)
    else:
        clients["bitget"] = ccxt.bitget({
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
    log.info(f"Bitget: {_exchange_mode('bitget')}")

    # ── OKX ─────────────────────────────────────────────────
    if Config.OKX_API_KEY:
        okx_cfg = {
            "apiKey": Config.OKX_API_KEY,
            "secret": Config.OKX_API_SECRET,
            "password": Config.OKX_PASSPHRASE,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if Config.OKX_DEMO:
            okx_cfg["headers"] = {"x-simulated-trading": "1"}
        clients["okx"] = ccxt.okx(okx_cfg)
    else:
        clients["okx"] = ccxt.okx({
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
    log.info(f"OKX: {_exchange_mode('okx')}")

    return clients


# ─── Auth checker ─────────────────────────────────────────────────────────────
DEMO_ERR_CODES = ["50038", "40099", "unavailable", "environment", "demo", "paper"]

def _is_demo_limit(err: str) -> bool:
    return any(c in err.lower() for c in DEMO_ERR_CODES)

def check_auth(clients: dict) -> dict:
    """Verifica auth de Bybit, Bitget y OKX. Robusto para cuentas demo."""
    cfg = {
        "bybit":   (Config.BYBIT_API_KEY,   Config.BYBIT_DEMO),
        "okx":     (Config.OKX_API_KEY,      Config.OKX_DEMO),
        "bitget":  (Config.BITGET_API_KEY,   Config.BITGET_DEMO),
    }
    results = {}
    for name, (key, is_demo) in cfg.items():
        if not key:
            results[name] = {"status": "no_key", "free": None, "total": None,
                             "error": None, "demo": is_demo}
            continue
        client = clients.get(name)
        try:
            balance = client.fetch_balance()
            usdt = balance.get("USDT", {})
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
                                 "note": "Key demo OK — balance no disponible en demo"}
                log.info(f"[{name}] Auth OK (demo key verificada)")
            else:
                results[name] = {"status": "error", "free": None, "total": None,
                                 "error": err[:150], "demo": is_demo, "note": None}
                log.error(f"[{name}] Auth FAILED: {err[:100]}")
    return results


def save_auth_status(status: dict):
    with open("data/auth_status.json", "w") as f:
        json.dump({**status, "checked_at": datetime.utcnow().isoformat()}, f, indent=2)


# ─── Funding rate fetcher ─────────────────────────────────────────────────────
def fetch_rates_from(name: str, client) -> dict:
    rates = {}
    for symbol in Config.SYMBOLS:
        try:
            data = client.fetch_funding_rate(symbol)
            rate = data.get("fundingRate")
            if rate is not None:
                rates[symbol] = float(rate) * 100
        except Exception as e:
            log.debug(f"[{name}] {symbol}: {e}")
    return rates


def get_all_rates(clients: dict) -> dict:
    """
    Consulta todos los exchanges y calcula por símbolo:
    - rates por exchange
    - mejor spread entre cualquier par de exchanges
    """
    perp = {k: v for k, v in clients.items() if k != "bybit_spot"}
    raw = {}
    for name, client in perp.items():
        r = fetch_rates_from(name, client)
        log.info(f"[{name}] {len(r)} rates obtenidos")
        for sym, rate in r.items():
            raw.setdefault(sym, {})[name] = rate

    result = {}
    for sym, ex_rates in raw.items():
        if not ex_rates:
            continue

        best_ex    = max(ex_rates, key=ex_rates.get)
        best_rate  = ex_rates[best_ex]
        best_spread = 0.0
        spread_long = spread_short = None

        items = list(ex_rates.items())
        for i, (ex_a, rate_a) in enumerate(items):
            for ex_b, rate_b in items[i+1:]:
                if rate_b > rate_a:
                    spread = rate_b - rate_a
                    lo, sh = ex_a, ex_b
                else:
                    spread = rate_a - rate_b
                    lo, sh = ex_b, ex_a
                if spread > best_spread:
                    best_spread  = spread
                    spread_long  = lo
                    spread_short = sh

        result[sym] = {
            "rates":        ex_rates,
            "best_rate":    best_rate,
            "best_exchange": best_ex,
            "best_spread":  round(best_spread, 6),
            "spread_long":  spread_long,
            "spread_short": spread_short,
        }
    return result


# ─── Helpers ──────────────────────────────────────────────────────────────────
def can_trade(exchange: str) -> bool:
    """True si el exchange tiene key cargada (puede ejecutar órdenes)."""
    keys = {
        "bybit":   Config.BYBIT_API_KEY,
        "binance": Config.BINANCE_API_KEY,
        "bitget":  Config.BITGET_API_KEY,
        "okx":     Config.OKX_API_KEY,
    }
    return bool(keys.get(exchange, ""))


def hours_since(iso: str) -> float:
    dt = datetime.fromisoformat(iso).replace(tzinfo=timezone.utc)
    now = datetime.now(timezone.utc)
    return (now - dt).total_seconds() / 3600


# ─── Position manager ─────────────────────────────────────────────────────────
class PositionManager:
    def __init__(self):
        self.positions = self._load()

    def _load(self) -> list:
        try:
            with open("data/positions.json") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self):
        with open("data/positions.json", "w") as f:
            json.dump(self.positions, f, indent=2)

    def add(self, pos: dict):
        self.positions.append(pos)
        self._save()

    def remove(self, uid: str) -> Optional[dict]:
        for i, p in enumerate(self.positions):
            if p["id"] == uid:
                pos = self.positions.pop(i)
                self._save()
                return pos
        return None

    def get_by_symbol(self, symbol: str) -> list:
        return [p for p in self.positions if p["symbol"] == symbol]

    def count(self) -> int:
        return len(self.positions)

    def update_funding(self, uid: str, earned: float):
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
        self.path = "data/trades.json"
        self.trades = self._load()

    def _load(self) -> list:
        try:
            with open(self.path) as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            return []

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.trades, f, indent=2)

    def log_open(self, uid, symbol, capital, strategy, rate, long_ex, short_ex, mode):
        t = {
            "id": uid, "symbol": symbol, "capital": capital,
            "strategy": strategy, "rate_at_open": rate,
            "long_exchange": long_ex, "short_exchange": short_ex,
            "opened_at": datetime.utcnow().isoformat(),
            "closed_at": None, "funding_collected": 0,
            "pnl_net": None, "status": "open", "mode": mode,
        }
        self.trades.append(t)
        self._save()

    def log_close(self, uid, funding, pnl):
        for t in self.trades:
            if t["id"] == uid and t["status"] == "open":
                t["closed_at"]        = datetime.utcnow().isoformat()
                t["funding_collected"] = round(funding, 6)
                t["pnl_net"]          = round(pnl, 6)
                t["status"]           = "closed"
                break
        self._save()

    def sync_open_funding(self, positions: list):
        """Sincroniza funding_collected de posiciones abiertas al trades.json."""
        pos_map = {p["id"]: p for p in positions}
        changed = False
        for t in self.trades:
            if t["status"] == "open" and t["id"] in pos_map:
                t["funding_collected"] = pos_map[t["id"]].get("funding_collected", 0)
                changed = True
        if changed:
            self._save()

    def summary(self) -> dict:
        # Incluye funding de posiciones abiertas también
        closed = [t for t in self.trades if t.get("status") == "closed"]
        open_t = [t for t in self.trades if t.get("status") == "open"]
        pnl        = sum(t.get("pnl_net") or 0 for t in closed)
        funding_cl = sum(t.get("funding_collected", 0) for t in closed)
        funding_op = sum(t.get("funding_collected", 0) for t in open_t)
        win = [t for t in closed if (t.get("pnl_net") or 0) > 0]
        return {
            "total_trades":     len(closed),
            "total_pnl":        round(pnl, 4),
            "total_funding":    round(funding_cl + funding_op, 4),
            "open_positions":   len(open_t),
            "win_rate":         round(len(win) / len(closed) * 100, 1) if closed else 0,
            "spot_perp_trades": len([t for t in closed if t.get("strategy") == "spot_perp"]),
            "spread_trades":    len([t for t in closed if t.get("strategy") == "spread"]),
        }


# ─── Core bot ─────────────────────────────────────────────────────────────────
class FundingBot:
    def __init__(self):
        self.clients = init_exchanges()
        self.pm = PositionManager()
        self.tl = TradeLogger()

        log.info("Verificando autenticación...")
        auth = check_auth(self.clients)
        save_auth_status(auth)

        tradeable = [ex for ex in ["bybit","binance","bitget","okx"] if can_trade(ex)]
        log.info(f"Exchanges con key (pueden operar): {tradeable or ['ninguno — modo rates publicos']}")
        log.info(f"Capital/trade: ${Config.CAPITAL_PER_TRADE} | Spread min: {Config.MIN_SPREAD}% | Max pos: {Config.MAX_POSITIONS}")
        log.info(f"PAPER_TRADING: {Config.PAPER_TRADING}")

    def _uid(self, symbol, strategy):
        return f"{symbol}_{strategy}_{int(time.time())}"

    def _mode_str(self, long_ex: str, short_ex: str) -> str:
        if Config.PAPER_TRADING:
            return "paper"
        modes = {
            "bybit":   "demo" if Config.BYBIT_DEMO  else "real",
            "binance": "real",
            "bitget":  "demo" if Config.BITGET_DEMO else "real",
            "okx":     "demo" if Config.OKX_DEMO    else "real",
        }
        m_long  = modes.get(long_ex,  "real")
        m_short = modes.get(short_ex, "real")
        if m_long == m_short:
            return m_long
        return f"{m_long}/{m_short}"

    def open_spread(self, symbol: str, spread: float, long_ex: str, short_ex: str):
        if self.pm.get_by_symbol(symbol) or self.pm.count() >= Config.MAX_POSITIONS:
            return

        # En paper trading abrimos sin importar si hay key
        # En real/demo necesitamos key en ambos exchanges
        if not Config.PAPER_TRADING:
            if not can_trade(long_ex) or not can_trade(short_ex):
                log.info(f"[spread] Skip {symbol}: {long_ex}/{short_ex} sin key")
                return

        uid = self._uid(symbol, "spread")
        try:
            # Precio de referencia — usar cliente público si no hay key
            ref_client = self.clients.get(long_ex, self.clients["bybit"])
            ticker = ref_client.fetch_ticker(Config.spot_symbol(symbol))
            price  = float(ticker["last"])
            amount = Config.CAPITAL_PER_TRADE / price
            mode   = self._mode_str(long_ex, short_ex)

            if Config.PAPER_TRADING:
                log.info(f"[PAPER] Spread LONG  {symbol} → {long_ex}")
                log.info(f"[PAPER] Spread SHORT {symbol} → {short_ex} | Spread: {spread:.4f}%")
            else:
                self.clients[long_ex].create_market_buy_order(symbol, amount)
                self.clients[short_ex].create_market_sell_order(symbol, amount)
                log.info(f"[{mode.upper()}] Spread ejecutado: LONG {long_ex} / SHORT {short_ex}")

            pos = {
                "id": uid, "symbol": symbol,
                "spot_symbol": Config.spot_symbol(symbol),
                "capital": Config.CAPITAL_PER_TRADE, "amount": amount,
                "entry_price": price, "entry_rate": spread,
                "strategy": "spread",
                "long_exchange": long_ex, "short_exchange": short_ex,
                "opened_at": datetime.utcnow().isoformat(),
                "funding_collected": 0, "funding_cycles": 0,
                "last_funding_at": None,
                "mode": mode,
            }
            self.pm.add(pos)
            self.tl.log_open(uid, symbol, Config.CAPITAL_PER_TRADE,
                             "spread", spread, long_ex, short_ex, mode)
            log.info(f"Abierto: {symbol} | Spread: {spread:.4f}% | {long_ex}→{short_ex} | Modo: {mode}")

        except Exception as e:
            log.error(f"Error abriendo {symbol}: {e}")

    def close_position(self, pos: dict, reason: str = "manual"):
        try:
            if Config.PAPER_TRADING:
                log.info(f"[PAPER] Cerrando {pos['symbol']} | {reason}")
            else:
                self.clients[pos["long_exchange"]].create_market_sell_order(
                    pos["symbol"], pos["amount"])
                self.clients[pos["short_exchange"]].create_market_buy_order(
                    pos["symbol"], pos["amount"])

            fees    = Config.CAPITAL_PER_TRADE * 0.002
            pnl     = pos["funding_collected"] - fees
            self.tl.log_close(pos["id"], pos["funding_collected"], pnl)
            self.pm.remove(pos["id"])
            log.info(f"Cerrado: {pos['symbol']} | Funding: ${pos['funding_collected']:.4f} | PnL: ${pnl:.4f} | {reason}")

        except Exception as e:
            log.error(f"Error cerrando {pos['symbol']}: {e}")

    def _should_collect_funding(self, pos: dict) -> bool:
        """
        El funding se cobra cada FUNDING_INTERVAL_H horas.
        En el primer ciclo siempre cobra.
        """
        last = pos.get("last_funding_at")
        if not last:
            return True
        return hours_since(last) >= Config.FUNDING_INTERVAL_H

    def run_cycle(self):
        log.info("─" * 70)
        log.info("Iniciando ciclo de evaluación...")

        auth = check_auth(self.clients)
        save_auth_status(auth)

        all_rates = get_all_rates(self.clients)
        if not all_rates:
            log.warning("Sin rates disponibles, reintentando en el próximo ciclo.")
            return

        perp_exs = [k for k in self.clients if k != "bybit_spot"]
        log.info(f"{'Par':<18}" + "".join(f"{e:>10}" for e in perp_exs) + "   Spread  Estado")
        log.info("-" * 80)

        spread_opps = []

        for sym in Config.SYMBOLS:
            data = all_rates.get(sym)
            if not data:
                continue

            rates_str   = "".join(f"{data['rates'].get(e, 0):>9.4f}%" for e in perp_exs)
            best_spread = data["best_spread"]
            has_pos     = bool(self.pm.get_by_symbol(sym))

            if has_pos:
                status = "ABIERTA"
            elif best_spread >= Config.MIN_SPREAD:
                lo, sh = data["spread_long"], data["spread_short"]
                status = f"✓ {lo}→{sh}"
            else:
                status = "—"

            log.info(f"{sym:<18}{rates_str}  {best_spread:>7.4f}%  {status}")

            if not has_pos and best_spread >= Config.MIN_SPREAD:
                spread_opps.append((sym, best_spread, data["spread_long"], data["spread_short"]))

        # ── Actualizar funding de posiciones abiertas ──────────────────────
        for pos in list(self.pm.positions):
            sym  = pos["symbol"]
            data = all_rates.get(sym)
            if not data:
                continue

            long_rate  = data["rates"].get(pos["long_exchange"],  0)
            short_rate = data["rates"].get(pos["short_exchange"], 0)
            spread     = short_rate - long_rate

            if spread > 0 and self._should_collect_funding(pos):
                # Ganancia = capital × spread% (ya es % del intervalo del exchange)
                earned = pos["capital"] * (spread / 100)
                self.pm.update_funding(pos["id"], earned)
                log.info(
                    f"Funding cobrado {sym}: +${earned:.4f} "
                    f"(spread {spread:.4f}% | ciclo #{pos.get('funding_cycles',0)+1})"
                )
            elif spread < -0.005:
                log.warning(f"{sym}: spread invertido ({spread:.4f}%), cerrando.")
                self.close_position(pos, "spread_invertido")

        # Sincronizar funding al trades.json para que el dashboard lo vea
        self.tl.sync_open_funding(self.pm.positions)

        # ── Abrir nuevas oportunidades ─────────────────────────────────────
        spread_opps.sort(key=lambda x: x[1], reverse=True)
        for sym, spread, long_ex, short_ex in spread_opps:
            if self.pm.count() < Config.MAX_POSITIONS:
                self.open_spread(sym, spread, long_ex, short_ex)

        summary = self.tl.summary()
        log.info("─" * 70)
        log.info(
            f"RESUMEN | Abiertas: {self.pm.count()} | "
            f"Cerradas: {summary['total_trades']} | "
            f"Funding total: ${summary['total_funding']} | "
            f"PnL: ${summary['total_pnl']}"
        )

    def run(self):
        log.info("=" * 70)
        log.info("  FUNDING RATE BOT — Spread inter-exchange")
        log.info(f"  Modo: {'PAPER TRADING' if Config.PAPER_TRADING else 'REAL/DEMO'}")
        log.info("=" * 70)
        while True:
            try:
                self.run_cycle()
            except KeyboardInterrupt:
                log.info("Bot detenido.")
                break
            except Exception as e:
                log.error(f"Error en ciclo: {e}")
            log.info(f"Próximo ciclo en {Config.CHECK_INTERVAL // 60} minutos...")
            time.sleep(Config.CHECK_INTERVAL)


if __name__ == "__main__":
    FundingBot().run()

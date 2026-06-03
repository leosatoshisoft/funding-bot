"""
Funding Rate Arbitrage Bot
- Bybit/Binance: APIs públicas para rates
- OKX + Bitget: modo real (o demo con sus APIs de testnet)
"""

import os
import time
import json
import logging
from datetime import datetime
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
    # Rates públicos (sin key)
    BYBIT_API_KEY      = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET   = os.getenv("BYBIT_API_SECRET", "")
    BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")

    # Operaciones reales / demo
    BITGET_API_KEY     = os.getenv("BITGET_API_KEY", "")
    BITGET_API_SECRET  = os.getenv("BITGET_API_SECRET", "")
    BITGET_PASSPHRASE  = os.getenv("BITGET_PASSPHRASE", "")
    BITGET_DEMO        = os.getenv("BITGET_DEMO", "true").lower() == "true"

    OKX_API_KEY        = os.getenv("OKX_API_KEY", "")
    OKX_API_SECRET     = os.getenv("OKX_API_SECRET", "")
    OKX_PASSPHRASE     = os.getenv("OKX_PASSPHRASE", "")
    OKX_DEMO           = os.getenv("OKX_DEMO", "true").lower() == "true"

    PAPER_TRADING      = os.getenv("PAPER_TRADING", "true").lower() == "true"
    MIN_FUNDING_RATE   = float(os.getenv("MIN_FUNDING_RATE", "0.02"))
    MIN_SPREAD         = float(os.getenv("MIN_SPREAD", "0.003"))
    CAPITAL_PER_TRADE  = float(os.getenv("CAPITAL_PER_TRADE", "500"))
    MAX_POSITIONS      = int(os.getenv("MAX_POSITIONS", "4"))
    CHECK_INTERVAL     = int(os.getenv("CHECK_INTERVAL", "3600"))

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
def init_exchanges() -> dict:
    clients = {}

    # Bybit — solo rates públicos
    clients["bybit_spot"] = ccxt.bybit({
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })
    clients["bybit"] = ccxt.bybit({
        "enableRateLimit": True,
        "options": {"defaultType": "linear"},
    })

    # Binance — solo rates públicos
    clients["binance"] = ccxt.binance({
        "enableRateLimit": True,
        "options": {"defaultType": "future"},
    })

    # Bitget — con key, modo demo o real
    if Config.BITGET_API_KEY:
        bitget_cfg = {
            "apiKey": Config.BITGET_API_KEY,
            "secret": Config.BITGET_API_SECRET,
            "password": Config.BITGET_PASSPHRASE,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if Config.BITGET_DEMO:
            # Bitget demo usa el mismo endpoint pero con header especial
            bitget_cfg["options"]["sandboxMode"] = True
        clients["bitget"] = ccxt.bitget(bitget_cfg)
        log.info(f"Bitget: {'DEMO' if Config.BITGET_DEMO else 'REAL'}")
    else:
        clients["bitget"] = ccxt.bitget({
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
        log.info("Bitget: sin key (solo rates públicos)")

    # OKX — con key, modo demo o real
    if Config.OKX_API_KEY:
        okx_cfg = {
            "apiKey": Config.OKX_API_KEY,
            "secret": Config.OKX_API_SECRET,
            "password": Config.OKX_PASSPHRASE,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        }
        if Config.OKX_DEMO:
            okx_cfg["sandbox"] = True  # OKX testnet
        clients["okx"] = ccxt.okx(okx_cfg)
        log.info(f"OKX: {'DEMO' if Config.OKX_DEMO else 'REAL'}")
    else:
        clients["okx"] = ccxt.okx({
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
        log.info("OKX: sin key (solo rates públicos)")

    return clients


# ─── Auth checker ─────────────────────────────────────────────────────────────
def check_auth(clients: dict) -> dict:
    """
    Verifica login y balance de OKX y Bitget.
    Devuelve dict con estado por exchange.
    """
    results = {}
    for name in ["okx", "bitget"]:
        client = clients.get(name)
        has_key = bool(
            Config.OKX_API_KEY if name == "okx" else Config.BITGET_API_KEY
        )
        if not has_key:
            results[name] = {"status": "no_key", "balance": None, "error": None}
            continue
        try:
            balance = client.fetch_balance()
            usdt = balance.get("USDT", {})
            free = float(usdt.get("free", 0))
            total = float(usdt.get("total", 0))
            results[name] = {
                "status": "ok",
                "free": round(free, 2),
                "total": round(total, 2),
                "error": None,
                "demo": Config.OKX_DEMO if name == "okx" else Config.BITGET_DEMO,
            }
            log.info(f"[{name}] Auth OK | Balance USDT: ${free:.2f} libre / ${total:.2f} total")
        except Exception as e:
            results[name] = {"status": "error", "balance": None, "error": str(e)[:120]}
            log.error(f"[{name}] Auth FAILED: {e}")
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
        best_ex = max(ex_rates, key=ex_rates.get)
        best_rate = ex_rates[best_ex]

        best_spread = 0.0
        spread_long = spread_short = None
        ex_list = list(ex_rates.items())
        for i, (ex_a, rate_a) in enumerate(ex_list):
            for ex_b, rate_b in ex_list[i+1:]:
                if rate_b > rate_a:
                    spread = rate_b - rate_a
                    long_ex, short_ex = ex_a, ex_b
                else:
                    spread = rate_a - rate_b
                    long_ex, short_ex = ex_b, ex_a
                if spread > best_spread:
                    best_spread = spread
                    spread_long = long_ex
                    spread_short = short_ex

        result[sym] = {
            "rates": ex_rates,
            "best_rate": best_rate,
            "best_exchange": best_ex,
            "best_spread": round(best_spread, 6),
            "spread_long": spread_long,
            "spread_short": spread_short,
        }
    return result


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
                t["closed_at"] = datetime.utcnow().isoformat()
                t["funding_collected"] = round(funding, 6)
                t["pnl_net"] = round(pnl, 6)
                t["status"] = "closed"
                break
        self._save()

    def summary(self) -> dict:
        closed = [t for t in self.trades if t.get("status") == "closed"]
        open_t = [t for t in self.trades if t.get("status") == "open"]
        pnl = sum(t.get("pnl_net") or 0 for t in closed)
        funding = sum(t.get("funding_collected", 0) for t in closed)
        win = [t for t in closed if (t.get("pnl_net") or 0) > 0]
        spot_perp = len([t for t in closed if t.get("strategy") == "spot_perp"])
        spread = len([t for t in closed if t.get("strategy") == "spread"])
        return {
            "total_trades": len(closed),
            "total_pnl": round(pnl, 4),
            "total_funding": round(funding, 4),
            "open_positions": len(open_t),
            "win_rate": round(len(win) / len(closed) * 100, 1) if closed else 0,
            "spot_perp_trades": spot_perp,
            "spread_trades": spread,
        }


# ─── Core bot ─────────────────────────────────────────────────────────────────
class FundingBot:
    def __init__(self):
        self.clients = init_exchanges()
        self.pm = PositionManager()
        self.tl = TradeLogger()

        # Verificar auth al arrancar
        log.info("Verificando autenticación de exchanges...")
        auth = check_auth(self.clients)
        save_auth_status(auth)

        log.info(f"Capital/trade: ${Config.CAPITAL_PER_TRADE} | Rate min: {Config.MIN_FUNDING_RATE}% | Spread min: {Config.MIN_SPREAD}% | Max pos: {Config.MAX_POSITIONS}")

    def _uid(self, symbol, strategy):
        return f"{symbol}_{strategy}_{int(time.time())}"

    def _can_trade(self, exchange: str) -> bool:
        """Solo opera en OKX y Bitget si tienen key. Resto solo rates."""
        if exchange in ("okx", "bitget"):
            key = Config.OKX_API_KEY if exchange == "okx" else Config.BITGET_API_KEY
            return bool(key)
        return False

    def open_spread(self, symbol: str, spread: float, long_ex: str, short_ex: str):
        existing = [p for p in self.pm.get_by_symbol(symbol) if p.get("strategy") == "spread"]
        if existing or self.pm.count() >= Config.MAX_POSITIONS:
            return

        # Solo opera si ambos exchanges tienen key
        if not self._can_trade(long_ex) or not self._can_trade(short_ex):
            log.info(f"[spread] {symbol}: {long_ex}/{short_ex} sin key, skip.")
            return

        uid = self._uid(symbol, "spread")
        try:
            ticker = self.clients[long_ex].fetch_ticker(Config.spot_symbol(symbol))
            price = float(ticker["last"])
            amount = Config.CAPITAL_PER_TRADE / price

            log.info(f"[spread] LONG  {symbol} → {long_ex}")
            log.info(f"[spread] SHORT {symbol} → {short_ex} | Spread: {spread:.4f}%")
            self.clients[long_ex].create_market_buy_order(symbol, amount)
            self.clients[short_ex].create_market_sell_order(symbol, amount)

            pos = {
                "id": uid, "symbol": symbol,
                "spot_symbol": Config.spot_symbol(symbol),
                "capital": Config.CAPITAL_PER_TRADE, "amount": amount,
                "entry_price": price, "entry_rate": spread,
                "strategy": "spread",
                "long_exchange": long_ex, "short_exchange": short_ex,
                "opened_at": datetime.utcnow().isoformat(), "funding_collected": 0,
                "mode": "demo" if (Config.OKX_DEMO or Config.BITGET_DEMO) else "real",
            }
            self.pm.add(pos)
            self.tl.log_open(uid, symbol, Config.CAPITAL_PER_TRADE, "spread",
                             spread, long_ex, short_ex, pos["mode"])
            log.info(f"[spread] Abierto: {symbol} | Spread: {spread:.4f}% | {long_ex} → {short_ex}")

        except Exception as e:
            log.error(f"Error abriendo spread {symbol}: {e}")

    def close_position(self, pos: dict, reason: str = "manual"):
        try:
            log.info(f"Cerrando {pos['strategy']} {pos['symbol']} | {reason}")
            if pos["strategy"] == "spread":
                self.clients[pos["long_exchange"]].create_market_sell_order(
                    pos["symbol"], pos["amount"])
                self.clients[pos["short_exchange"]].create_market_buy_order(
                    pos["symbol"], pos["amount"])

            fees = Config.CAPITAL_PER_TRADE * 0.002
            pnl = pos["funding_collected"] - fees
            self.tl.log_close(pos["id"], pos["funding_collected"], pnl)
            self.pm.remove(pos["id"])
            log.info(f"Cerrado: {pos['symbol']} | Funding: ${pos['funding_collected']:.4f} | PnL: ${pnl:.4f}")

        except Exception as e:
            log.error(f"Error cerrando {pos['symbol']}: {e}")

    def run_cycle(self):
        log.info("─" * 70)
        log.info("Iniciando ciclo...")

        # Re-verificar auth cada ciclo y guardar estado
        auth = check_auth(self.clients)
        save_auth_status(auth)

        all_rates = get_all_rates(self.clients)
        if not all_rates:
            log.warning("Sin rates disponibles.")
            return

        perp_exs = [k for k in self.clients if k != "bybit_spot"]
        log.info(f"{'Par':<18}" + "".join(f"{e:>10}" for e in perp_exs) + f"{'Spread':>9}  Estado")
        log.info("-" * 75)

        spread_opps = []

        for sym in Config.SYMBOLS:
            data = all_rates.get(sym)
            if not data:
                continue
            rates_str = "".join(f"{data['rates'].get(e, 0):>9.4f}%" for e in perp_exs)
            best_spread = data["best_spread"]
            has_pos = bool(self.pm.get_by_symbol(sym))
            status = "ABIERTA" if has_pos else (
                f"✓ spread({data['spread_long']}→{data['spread_short']})"
                if best_spread >= Config.MIN_SPREAD else "—"
            )
            log.info(f"{sym:<18}{rates_str}  {best_spread:>7.4f}%  {status}")

            if not has_pos and best_spread >= Config.MIN_SPREAD:
                long_ex = data["spread_long"]
                short_ex = data["spread_short"]
                if self._can_trade(long_ex) and self._can_trade(short_ex):
                    spread_opps.append((sym, best_spread, long_ex, short_ex))

        # Actualizar funding de posiciones abiertas
        for pos in list(self.pm.positions):
            sym = pos["symbol"]
            data = all_rates.get(sym)
            if not data:
                continue
            long_rate = data["rates"].get(pos["long_exchange"], 0)
            short_rate = data["rates"].get(pos["short_exchange"], 0)
            spread = short_rate - long_rate
            if spread > 0:
                earned = pos["capital"] * (spread / 100)
                self.pm.update_funding(pos["id"], earned)
                log.info(f"Funding {sym}: +${earned:.4f} (spread {spread:.4f}%)")
            elif spread < -0.005:
                self.close_position(pos, "spread_invertido")

        # Abrir oportunidades
        spread_opps.sort(key=lambda x: x[1], reverse=True)
        for sym, spread, long_ex, short_ex in spread_opps:
            if self.pm.count() < Config.MAX_POSITIONS:
                self.open_spread(sym, spread, long_ex, short_ex)

        summary = self.tl.summary()
        log.info("─" * 70)
        log.info(f"RESUMEN | Abiertas: {self.pm.count()} | PnL: ${summary['total_pnl']} | Funding: ${summary['total_funding']}")

    def run(self):
        log.info("=" * 70)
        log.info("  FUNDING RATE BOT — Spread inter-exchange OKX + Bitget")
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

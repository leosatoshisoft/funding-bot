"""
Funding Rate Arbitrage Bot
Estrategia 1: Spot Bybit + mejor perp (rate positivo alto)
Estrategia 2: Spread inter-exchange (long perp A + short perp B)
APIs públicas — keys solo necesarias en modo real
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
    BYBIT_API_KEY      = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET   = os.getenv("BYBIT_API_SECRET", "")
    BINANCE_API_KEY    = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET = os.getenv("BINANCE_API_SECRET", "")
    BITGET_API_KEY     = os.getenv("BITGET_API_KEY", "")
    BITGET_API_SECRET  = os.getenv("BITGET_API_SECRET", "")
    BITGET_PASSPHRASE  = os.getenv("BITGET_PASSPHRASE", "")
    OKX_API_KEY        = os.getenv("OKX_API_KEY", "")
    OKX_API_SECRET     = os.getenv("OKX_API_SECRET", "")
    OKX_PASSPHRASE     = os.getenv("OKX_PASSPHRASE", "")

    PAPER_TRADING      = os.getenv("PAPER_TRADING", "true").lower() == "true"
    MIN_FUNDING_RATE   = float(os.getenv("MIN_FUNDING_RATE", "0.02"))
    MIN_SPREAD         = float(os.getenv("MIN_SPREAD", "0.003"))   # % spread inter-exchange
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
    def make(cls, key, secret, extra=None, opts=None):
        cfg = {"enableRateLimit": True, "options": opts or {}}
        if key:
            cfg["apiKey"] = key
            cfg["secret"] = secret
            if extra:
                cfg["password"] = extra
        return cls(cfg)

    clients = {
        "bybit_spot": make(ccxt.bybit, Config.BYBIT_API_KEY, Config.BYBIT_API_SECRET,
                           opts={"defaultType": "spot"}),
        "bybit":      make(ccxt.bybit, Config.BYBIT_API_KEY, Config.BYBIT_API_SECRET,
                           opts={"defaultType": "linear"}),
        "binance":    make(ccxt.binance, Config.BINANCE_API_KEY, Config.BINANCE_API_SECRET,
                           opts={"defaultType": "future"}),
        "bitget":     make(ccxt.bitget, Config.BITGET_API_KEY, Config.BITGET_API_SECRET,
                           extra=Config.BITGET_PASSPHRASE, opts={"defaultType": "swap"}),
        "okx":        make(ccxt.okx, Config.OKX_API_KEY, Config.OKX_API_SECRET,
                           extra=Config.OKX_PASSPHRASE, opts={"defaultType": "swap"}),
    }
    log.info(f"Exchanges listos | Modo: {'PAPER' if Config.PAPER_TRADING else 'REAL'}")
    return clients


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
    Devuelve por símbolo:
    {
      "rates": {"bybit": 0.01, "binance": 0.03, ...},
      "best_rate": 0.03,
      "best_exchange": "binance",
      "best_spread": 0.025,          # mayor diferencia entre 2 exchanges
      "spread_long": "bitget",        # exchange donde hacer el long
      "spread_short": "binance",      # exchange donde hacer el short
    }
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
        best_ex = max(ex_rates, key=ex_rates.get)
        best_rate = ex_rates[best_ex]

        # Calcular mejor spread inter-exchange (normalizado a /h de 8hs)
        best_spread = 0.0
        spread_long = spread_short = None
        ex_list = list(ex_rates.items())
        for i, (ex_a, rate_a) in enumerate(ex_list):
            for ex_b, rate_b in ex_list[i+1:]:
                # short en el que paga más, long en el que paga menos
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
            "id": uid,
            "symbol": symbol,
            "capital": capital,
            "strategy": strategy,   # "spot_perp" | "spread"
            "rate_at_open": rate,
            "long_exchange": long_ex,
            "short_exchange": short_ex,
            "opened_at": datetime.utcnow().isoformat(),
            "closed_at": None,
            "funding_collected": 0,
            "pnl_net": None,
            "status": "open",
            "mode": mode,
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
        return {
            "total_trades": len(closed),
            "total_pnl": round(pnl, 4),
            "total_funding": round(funding, 4),
            "open_positions": len(open_t),
            "win_rate": round(len(win) / len(closed) * 100, 1) if closed else 0,
        }


# ─── Core bot ─────────────────────────────────────────────────────────────────
class FundingBot:
    def __init__(self):
        self.clients = init_exchanges()
        self.pm = PositionManager()
        self.tl = TradeLogger()
        log.info(f"Capital/trade: ${Config.CAPITAL_PER_TRADE} | Rate min: {Config.MIN_FUNDING_RATE}% | Spread min: {Config.MIN_SPREAD}% | Max pos: {Config.MAX_POSITIONS}")

    def _uid(self, symbol, strategy):
        return f"{symbol}_{strategy}_{int(time.time())}"

    def open_spot_perp(self, symbol: str, rate: float, perp_ex: str):
        """Estrategia 1: compra spot Bybit + short perp en mejor exchange."""
        if self.pm.get_by_symbol(symbol):
            return
        if self.pm.count() >= Config.MAX_POSITIONS:
            return

        spot_sym = Config.spot_symbol(symbol)
        uid = self._uid(symbol, "spot_perp")
        try:
            ticker = self.clients["bybit_spot"].fetch_ticker(spot_sym)
            spot_price = float(ticker["last"])
            amount = Config.CAPITAL_PER_TRADE / spot_price

            if Config.PAPER_TRADING:
                log.info(f"[PAPER] Spot BUY  {spot_sym} @ ${spot_price:.2f} → Bybit")
                log.info(f"[PAPER] Perp SHORT {symbol} → {perp_ex} | Rate: {rate:.4f}%")
            else:
                self.clients["bybit_spot"].create_market_buy_order(spot_sym, amount)
                self.clients[perp_ex].create_market_sell_order(symbol, amount)

            pos = {
                "id": uid, "symbol": symbol, "spot_symbol": spot_sym,
                "capital": Config.CAPITAL_PER_TRADE, "amount": amount,
                "entry_price": spot_price, "entry_rate": rate,
                "strategy": "spot_perp",
                "long_exchange": "bybit_spot", "short_exchange": perp_ex,
                "opened_at": datetime.utcnow().isoformat(), "funding_collected": 0,
            }
            self.pm.add(pos)
            self.tl.log_open(uid, symbol, Config.CAPITAL_PER_TRADE, "spot_perp",
                             rate, "bybit", perp_ex, "paper" if Config.PAPER_TRADING else "real")
            log.info(f"[spot_perp] Abierto: {symbol} | Rate: {rate:.4f}% | Perp: {perp_ex}")

        except Exception as e:
            log.error(f"Error abriendo spot_perp {symbol}: {e}")

    def open_spread(self, symbol: str, spread: float, long_ex: str, short_ex: str):
        """Estrategia 2: long perp en exchange A + short perp en exchange B."""
        existing = [p for p in self.pm.get_by_symbol(symbol) if p.get("strategy") == "spread"]
        if existing:
            return
        if self.pm.count() >= Config.MAX_POSITIONS:
            return

        uid = self._uid(symbol, "spread")
        try:
            ticker = self.clients[long_ex].fetch_ticker(Config.spot_symbol(symbol))
            price = float(ticker["last"])
            amount = Config.CAPITAL_PER_TRADE / price

            if Config.PAPER_TRADING:
                log.info(f"[PAPER] Spread LONG  {symbol} → {long_ex}")
                log.info(f"[PAPER] Spread SHORT {symbol} → {short_ex} | Spread: {spread:.4f}%")
            else:
                self.clients[long_ex].create_market_buy_order(symbol, amount)
                self.clients[short_ex].create_market_sell_order(symbol, amount)

            pos = {
                "id": uid, "symbol": symbol, "spot_symbol": Config.spot_symbol(symbol),
                "capital": Config.CAPITAL_PER_TRADE, "amount": amount,
                "entry_price": price, "entry_rate": spread,
                "strategy": "spread",
                "long_exchange": long_ex, "short_exchange": short_ex,
                "opened_at": datetime.utcnow().isoformat(), "funding_collected": 0,
            }
            self.pm.add(pos)
            self.tl.log_open(uid, symbol, Config.CAPITAL_PER_TRADE, "spread",
                             spread, long_ex, short_ex, "paper" if Config.PAPER_TRADING else "real")
            log.info(f"[spread] Abierto: {symbol} | Spread: {spread:.4f}% | Long: {long_ex} → Short: {short_ex}")

        except Exception as e:
            log.error(f"Error abriendo spread {symbol}: {e}")

    def close_position(self, pos: dict, reason: str = "manual"):
        try:
            if Config.PAPER_TRADING:
                log.info(f"[PAPER] Cerrando {pos['strategy']} {pos['symbol']} | Razón: {reason}")
            else:
                if pos["strategy"] == "spot_perp":
                    self.clients["bybit_spot"].create_market_sell_order(
                        pos["spot_symbol"], pos["amount"])
                    self.clients[pos["short_exchange"]].create_market_buy_order(
                        pos["symbol"], pos["amount"])
                else:
                    self.clients[pos["long_exchange"]].create_market_sell_order(
                        pos["symbol"], pos["amount"])
                    self.clients[pos["short_exchange"]].create_market_buy_order(
                        pos["symbol"], pos["amount"])

            fees = Config.CAPITAL_PER_TRADE * 0.002
            pnl = pos["funding_collected"] - fees
            self.tl.log_close(pos["id"], pos["funding_collected"], pnl)
            self.pm.remove(pos["id"])
            log.info(f"Cerrado: {pos['symbol']} [{pos['strategy']}] | Funding: ${pos['funding_collected']:.4f} | PnL: ${pnl:.4f} | {reason}")

        except Exception as e:
            log.error(f"Error cerrando {pos['symbol']}: {e}")

    def run_cycle(self):
        log.info("─" * 70)
        log.info("Iniciando ciclo...")

        all_rates = get_all_rates(self.clients)
        if not all_rates:
            log.warning("Sin rates disponibles, reintentando en el próximo ciclo.")
            return

        perp_exs = [k for k in self.clients if k != "bybit_spot"]
        header = f"{'Par':<18}" + "".join(f"{e:>10}" for e in perp_exs) + f"{'Spread':>9}  Estrategia"
        log.info(header)
        log.info("-" * 75)

        spot_perp_opps = []
        spread_opps = []

        for sym in Config.SYMBOLS:
            data = all_rates.get(sym)
            if not data:
                continue
            rates_str = "".join(f"{data['rates'].get(e, 0):>9.4f}%" for e in perp_exs)
            best_rate = data["best_rate"]
            best_spread = data["best_spread"]
            has_pos = bool(self.pm.get_by_symbol(sym))

            strat = []
            if best_rate >= Config.MIN_FUNDING_RATE:
                strat.append(f"spot_perp({data['best_exchange']})")
            if best_spread >= Config.MIN_SPREAD:
                strat.append(f"spread({data['spread_long']}→{data['spread_short']})")
            strat_str = " + ".join(strat) if strat else "—"
            if has_pos:
                strat_str = "ABIERTA"

            log.info(f"{sym:<18}{rates_str}  {best_spread:>7.4f}%  {strat_str}")

            if not has_pos:
                if best_rate >= Config.MIN_FUNDING_RATE:
                    spot_perp_opps.append((sym, best_rate, data["best_exchange"]))
                if best_spread >= Config.MIN_SPREAD and data["spread_long"] and data["spread_short"]:
                    spread_opps.append((sym, best_spread, data["spread_long"], data["spread_short"]))

        # Actualizar funding de posiciones abiertas
        for pos in list(self.pm.positions):
            sym = pos["symbol"]
            data = all_rates.get(sym)
            if not data:
                continue
            if pos["strategy"] == "spot_perp":
                rate = data["rates"].get(pos["short_exchange"], 0)
                if rate > 0:
                    earned = pos["capital"] * (rate / 100)
                    self.pm.update_funding(pos["id"], earned)
                    log.info(f"Funding {sym} [spot_perp]: +${earned:.4f} ({rate:.4f}%)")
                elif rate < 0:
                    self.close_position(pos, "rate_negativo")
            else:
                long_rate = data["rates"].get(pos["long_exchange"], 0)
                short_rate = data["rates"].get(pos["short_exchange"], 0)
                spread = short_rate - long_rate
                if spread > 0:
                    earned = pos["capital"] * (spread / 100)
                    self.pm.update_funding(pos["id"], earned)
                    log.info(f"Funding {sym} [spread]: +${earned:.4f} (spread {spread:.4f}%)")
                elif spread < -0.005:
                    self.close_position(pos, "spread_invertido")

        # Abrir oportunidades — spread primero (más rentable ahora mismo)
        spread_opps.sort(key=lambda x: x[1], reverse=True)
        spot_perp_opps.sort(key=lambda x: x[1], reverse=True)

        for sym, spread, long_ex, short_ex in spread_opps:
            if self.pm.count() < Config.MAX_POSITIONS:
                self.open_spread(sym, spread, long_ex, short_ex)

        for sym, rate, perp_ex in spot_perp_opps:
            if self.pm.count() < Config.MAX_POSITIONS:
                self.open_spot_perp(sym, rate, perp_ex)

        summary = self.tl.summary()
        log.info("─" * 70)
        log.info(f"RESUMEN | Abiertas: {self.pm.count()} | Cerradas: {summary['total_trades']} | PnL: ${summary['total_pnl']} | Funding: ${summary['total_funding']}")

    def run(self):
        log.info("=" * 70)
        log.info("  FUNDING RATE BOT — Estrategia spot/perp + spread inter-exchange")
        log.info(f"  Modo: {'PAPER TRADING' if Config.PAPER_TRADING else 'REAL MONEY'}")
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

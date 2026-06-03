"""
Funding Rate Arbitrage Bot
Spot en Bybit + mejor perp entre Bybit / Binance / Bitget / OKX
APIs públicas para rates — keys solo necesarias en modo real
"""

import os
import time
import json
import logging
from datetime import datetime
from typing import Optional
import ccxt

# ─── Logging ─────────────────────────────────────────────────────────────────
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
    BYBIT_API_KEY       = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET    = os.getenv("BYBIT_API_SECRET", "")
    BINANCE_API_KEY     = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET  = os.getenv("BINANCE_API_SECRET", "")
    BITGET_API_KEY      = os.getenv("BITGET_API_KEY", "")
    BITGET_API_SECRET   = os.getenv("BITGET_API_SECRET", "")
    BITGET_PASSPHRASE   = os.getenv("BITGET_PASSPHRASE", "")
    OKX_API_KEY         = os.getenv("OKX_API_KEY", "")
    OKX_API_SECRET      = os.getenv("OKX_API_SECRET", "")
    OKX_PASSPHRASE      = os.getenv("OKX_PASSPHRASE", "")

    PAPER_TRADING       = os.getenv("PAPER_TRADING", "true").lower() == "true"
    MIN_FUNDING_RATE    = float(os.getenv("MIN_FUNDING_RATE", "0.02"))
    CAPITAL_PER_TRADE   = float(os.getenv("CAPITAL_PER_TRADE", "500"))
    MAX_POSITIONS       = int(os.getenv("MAX_POSITIONS", "3"))
    CHECK_INTERVAL      = int(os.getenv("CHECK_INTERVAL", "3600"))

    SYMBOLS = [
        "BTC/USDT:USDT",
        "ETH/USDT:USDT",
        "SOL/USDT:USDT",
        "BNB/USDT:USDT",
        "XRP/USDT:USDT",
        "DOGE/USDT:USDT",
        "AVAX/USDT:USDT",
        "LINK/USDT:USDT",
        "OP/USDT:USDT",
        "ARB/USDT:USDT",
        "SUI/USDT:USDT",
        "TON/USDT:USDT",
        "INJ/USDT:USDT",
        "NEAR/USDT:USDT",
    ]

    @staticmethod
    def spot_symbol(sym: str) -> str:
        return sym.split(":")[0]


# ─── Exchange clients ─────────────────────────────────────────────────────────
def init_exchanges() -> dict:
    clients = {}

    # Bybit spot — para ejecutar compras (modo real)
    clients["bybit_spot"] = ccxt.bybit({
        "apiKey": Config.BYBIT_API_KEY,
        "secret": Config.BYBIT_API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })

    # Bybit perp — rates públicos + órdenes en modo real
    clients["bybit"] = ccxt.bybit({
        "apiKey": Config.BYBIT_API_KEY,
        "secret": Config.BYBIT_API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "linear"},
    })

    # Binance perp (opcional)
    if Config.BINANCE_API_KEY:
        clients["binance"] = ccxt.binance({
            "apiKey": Config.BINANCE_API_KEY,
            "secret": Config.BINANCE_API_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })
    else:
        # Rates públicos sin key
        clients["binance"] = ccxt.binance({
            "enableRateLimit": True,
            "options": {"defaultType": "future"},
        })

    # Bitget perp (opcional)
    if Config.BITGET_API_KEY:
        clients["bitget"] = ccxt.bitget({
            "apiKey": Config.BITGET_API_KEY,
            "secret": Config.BITGET_API_SECRET,
            "password": Config.BITGET_PASSPHRASE,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
    else:
        clients["bitget"] = ccxt.bitget({
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })

    # OKX perp (opcional)
    if Config.OKX_API_KEY:
        clients["okx"] = ccxt.okx({
            "apiKey": Config.OKX_API_KEY,
            "secret": Config.OKX_API_SECRET,
            "password": Config.OKX_PASSPHRASE,
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })
    else:
        clients["okx"] = ccxt.okx({
            "enableRateLimit": True,
            "options": {"defaultType": "swap"},
        })

    mode = "PAPER TRADING" if Config.PAPER_TRADING else "REAL MONEY"
    log.info(f"Exchanges inicializados | Modo: {mode}")
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


def get_all_funding_rates(clients: dict) -> dict:
    perp_clients = {k: v for k, v in clients.items() if k != "bybit_spot"}
    all_rates = {}

    for name, client in perp_clients.items():
        r = fetch_rates_from(name, client)
        log.info(f"[{name}] {len(r)} rates obtenidos")
        for symbol, rate in r.items():
            if symbol not in all_rates:
                all_rates[symbol] = {"rates": {}}
            all_rates[symbol]["rates"][name] = rate

    result = {}
    for symbol, data in all_rates.items():
        rates = data["rates"]
        if not rates:
            continue
        best_exchange = max(rates, key=rates.get)
        best_rate = rates[best_exchange]
        result[symbol] = {
            "best_rate": best_rate,
            "best_exchange": best_exchange,
            "rates": rates,
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

    def add(self, position: dict):
        self.positions.append(position)
        self._save()

    def remove(self, symbol: str) -> Optional[dict]:
        for i, p in enumerate(self.positions):
            if p["symbol"] == symbol:
                pos = self.positions.pop(i)
                self._save()
                return pos
        return None

    def get(self, symbol: str) -> Optional[dict]:
        return next((p for p in self.positions if p["symbol"] == symbol), None)

    def count(self) -> int:
        return len(self.positions)

    def symbols(self) -> list:
        return [p["symbol"] for p in self.positions]

    def update_funding(self, symbol: str, earned: float):
        pos = self.get(symbol)
        if pos:
            pos["funding_collected"] = round(
                pos.get("funding_collected", 0) + earned, 6
            )
            self._save()


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

    def log_open(self, symbol, capital, rate, spot_price, perp_exchange, mode):
        trade = {
            "id": int(time.time()),
            "symbol": symbol,
            "capital": capital,
            "rate_at_open": rate,
            "spot_price": spot_price,
            "spot_exchange": "bybit",
            "perp_exchange": perp_exchange,
            "opened_at": datetime.utcnow().isoformat(),
            "closed_at": None,
            "funding_collected": 0,
            "pnl_net": None,
            "status": "open",
            "mode": mode,
        }
        self.trades.append(trade)
        self._save()
        return trade

    def log_close(self, symbol, funding_collected, pnl_net):
        for t in reversed(self.trades):
            if t["symbol"] == symbol and t["status"] == "open":
                t["closed_at"] = datetime.utcnow().isoformat()
                t["funding_collected"] = round(funding_collected, 6)
                t["pnl_net"] = round(pnl_net, 6)
                t["status"] = "closed"
                break
        self._save()

    def summary(self) -> dict:
        closed = [t for t in self.trades if t.get("status") == "closed"]
        open_t = [t for t in self.trades if t.get("status") == "open"]
        total_pnl = sum(t.get("pnl_net") or 0 for t in closed)
        total_funding = sum(t.get("funding_collected", 0) for t in closed)
        win = [t for t in closed if (t.get("pnl_net") or 0) > 0]
        return {
            "total_trades": len(closed),
            "total_pnl": round(total_pnl, 4),
            "total_funding": round(total_funding, 4),
            "open_positions": len(open_t),
            "win_rate": round(len(win) / len(closed) * 100, 1) if closed else 0,
        }


# ─── Core bot ─────────────────────────────────────────────────────────────────
class FundingBot:
    def __init__(self):
        self.clients = init_exchanges()
        self.pm = PositionManager()
        self.tl = TradeLogger()
        log.info(f"Capital/trade: ${Config.CAPITAL_PER_TRADE} | Rate mínimo: {Config.MIN_FUNDING_RATE}% | Max pos: {Config.MAX_POSITIONS}")

    def get_spot_price(self, symbol: str) -> float:
        spot_sym = Config.spot_symbol(symbol)
        ticker = self.clients["bybit_spot"].fetch_ticker(spot_sym)
        return float(ticker["last"])

    def open_position(self, symbol: str, rate: float, perp_exchange: str):
        if self.pm.get(symbol):
            return
        if self.pm.count() >= Config.MAX_POSITIONS:
            log.warning(f"Máximo de posiciones alcanzado ({Config.MAX_POSITIONS})")
            return

        try:
            spot_sym = Config.spot_symbol(symbol)
            spot_price = self.get_spot_price(symbol)
            amount = Config.CAPITAL_PER_TRADE / spot_price

            if Config.PAPER_TRADING:
                log.info(f"[PAPER] Spot BUY  {spot_sym}: {amount:.6f} @ ${spot_price:.2f} → Bybit")
                log.info(f"[PAPER] Perp SHORT {symbol}: {amount:.6f} @ ${spot_price:.2f} → {perp_exchange}")
            else:
                self.clients["bybit_spot"].create_market_buy_order(spot_sym, amount)
                log.info(f"[REAL] Spot BUY: {spot_sym} {amount:.6f} en Bybit")
                self.clients[perp_exchange].create_market_sell_order(symbol, amount)
                log.info(f"[REAL] Perp SHORT: {symbol} {amount:.6f} en {perp_exchange}")

            position = {
                "symbol": symbol,
                "spot_symbol": spot_sym,
                "capital": Config.CAPITAL_PER_TRADE,
                "amount": amount,
                "entry_price": spot_price,
                "entry_rate": rate,
                "perp_exchange": perp_exchange,
                "opened_at": datetime.utcnow().isoformat(),
                "funding_collected": 0,
            }
            self.pm.add(position)
            self.tl.log_open(
                symbol, Config.CAPITAL_PER_TRADE, rate, spot_price, perp_exchange,
                "paper" if Config.PAPER_TRADING else "real"
            )
            log.info(f"Posición abierta: {symbol} | Rate: {rate:.4f}% | Perp: {perp_exchange}")

        except Exception as e:
            log.error(f"Error al abrir posición {symbol}: {e}")

    def close_position(self, symbol: str, reason: str = "manual"):
        pos = self.pm.get(symbol)
        if not pos:
            return

        try:
            perp_ex = pos.get("perp_exchange", "bybit")

            if Config.PAPER_TRADING:
                log.info(f"[PAPER] Spot SELL {pos['spot_symbol']}: {pos['amount']:.6f} → Bybit")
                log.info(f"[PAPER] Perp CLOSE {symbol}: {pos['amount']:.6f} → {perp_ex}")
            else:
                self.clients["bybit_spot"].create_market_sell_order(
                    pos["spot_symbol"], pos["amount"]
                )
                self.clients[perp_ex].create_market_buy_order(symbol, pos["amount"])

            fees = Config.CAPITAL_PER_TRADE * 0.002
            pnl_net = pos["funding_collected"] - fees
            self.tl.log_close(symbol, pos["funding_collected"], pnl_net)
            self.pm.remove(symbol)
            log.info(
                f"Posición cerrada: {symbol} | "
                f"Funding: ${pos['funding_collected']:.4f} | "
                f"PnL: ${pnl_net:.4f} | Razón: {reason}"
            )

        except Exception as e:
            log.error(f"Error al cerrar posición {symbol}: {e}")

    def run_cycle(self):
        log.info("─" * 65)
        log.info("Iniciando ciclo de evaluación...")

        all_rates = get_all_funding_rates(self.clients)

        if not all_rates:
            log.warning("No se pudieron obtener funding rates, reintentando en el próximo ciclo.")
            return

        exchanges = [k for k in self.clients if k != "bybit_spot"]
        header = f"{'Par':<18}" + "".join(f"{ex:>10}" for ex in exchanges) + f"{'Mejor':>10}  Estado"
        log.info(header)
        log.info("-" * 70)

        opportunities = []

        for symbol in Config.SYMBOLS:
            data = all_rates.get(symbol)
            if not data:
                continue
            rates_str = "".join(
                f"{data['rates'].get(ex, 0):>9.4f}%" for ex in exchanges
            )
            best_rate = data["best_rate"]
            best_ex = data["best_exchange"]
            already = symbol in self.pm.symbols()
            status = "ABIERTA" if already else (
                "✓ OPORTUNIDAD" if best_rate >= Config.MIN_FUNDING_RATE else "—"
            )
            log.info(f"{symbol:<18}{rates_str}  {best_rate:>8.4f}%  {status} [{best_ex}]")

            if best_rate >= Config.MIN_FUNDING_RATE and not already:
                opportunities.append((symbol, best_rate, best_ex))

        # Actualizar funding de posiciones abiertas
        for sym in list(self.pm.symbols()):
            data = all_rates.get(sym)
            if not data:
                continue
            pos = self.pm.get(sym)
            perp_ex = pos.get("perp_exchange", "bybit")
            rate = data["rates"].get(perp_ex, data["best_rate"])

            if rate > 0:
                earned = pos["capital"] * (rate / 100)
                self.pm.update_funding(sym, earned)
                log.info(f"Funding cobrado {sym}: +${earned:.4f} ({rate:.4f}% en {perp_ex})")
            elif rate < 0:
                log.warning(f"{sym}: rate negativo ({rate:.4f}%), cerrando.")
                self.close_position(sym, reason="rate_negativo")

        # Abrir nuevas oportunidades
        opportunities.sort(key=lambda x: x[1], reverse=True)
        for sym, rate, best_ex in opportunities:
            if self.pm.count() < Config.MAX_POSITIONS:
                log.info(f"Abriendo: {sym} | Rate: {rate:.4f}% | Perp: {best_ex}")
                self.open_position(sym, rate, best_ex)

        summary = self.tl.summary()
        log.info("─" * 65)
        log.info(
            f"RESUMEN | Abiertas: {self.pm.count()} | "
            f"Cerradas: {summary['total_trades']} | "
            f"PnL: ${summary['total_pnl']} | "
            f"Funding: ${summary['total_funding']}"
        )

    def run(self):
        log.info("=" * 65)
        log.info("  FUNDING RATE BOT — Bybit/Binance/Bitget/OKX")
        log.info(f"  Modo: {'PAPER TRADING' if Config.PAPER_TRADING else 'REAL MONEY'}")
        log.info("=" * 65)

        while True:
            try:
                self.run_cycle()
            except KeyboardInterrupt:
                log.info("Bot detenido manualmente.")
                break
            except Exception as e:
                log.error(f"Error en ciclo principal: {e}")

            log.info(f"Próximo ciclo en {Config.CHECK_INTERVAL // 60} minutos...")
            time.sleep(Config.CHECK_INTERVAL)


if __name__ == "__main__":
    bot = FundingBot()
    bot.run()

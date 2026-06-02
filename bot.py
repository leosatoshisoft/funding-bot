"""
Funding Rate Arbitrage Bot
Bybit (spot) + Binance (perp) — delta neutral
"""

import os
import time
import json
import logging
from datetime import datetime
from typing import Optional
import ccxt

# ─── Logging ────────────────────────────────────────────────────────────────
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


# ─── Config ─────────────────────────────────────────────────────────────────
class Config:
    # Exchange API keys (se cargan desde variables de entorno)
    BYBIT_API_KEY     = os.getenv("BYBIT_API_KEY", "")
    BYBIT_API_SECRET  = os.getenv("BYBIT_API_SECRET", "")
    BINANCE_API_KEY   = os.getenv("BINANCE_API_KEY", "")
    BINANCE_API_SECRET= os.getenv("BINANCE_API_SECRET", "")

    # Modo: True = paper trading (sin órdenes reales), False = real
    PAPER_TRADING     = os.getenv("PAPER_TRADING", "true").lower() == "true"

    # Estrategia
    MIN_FUNDING_RATE  = float(os.getenv("MIN_FUNDING_RATE", "0.02"))   # % mínimo para entrar
    CAPITAL_PER_TRADE = float(os.getenv("CAPITAL_PER_TRADE", "500"))   # USDT por operación
    MAX_POSITIONS     = int(os.getenv("MAX_POSITIONS", "3"))            # máx posiciones abiertas
    CHECK_INTERVAL    = int(os.getenv("CHECK_INTERVAL", "3600"))        # segundos entre checks (1h)

    # Pares a monitorear
    SYMBOLS = [
        "BTC/USDT", "ETH/USDT", "SOL/USDT", "BNB/USDT",
        "XRP/USDT", "DOGE/USDT", "AVAX/USDT", "LINK/USDT",
        "ADA/USDT", "DOT/USDT",
    ]


# ─── Exchange clients ────────────────────────────────────────────────────────
def init_exchanges():
    bybit = ccxt.bybit({
        "apiKey": Config.BYBIT_API_KEY,
        "secret": Config.BYBIT_API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "spot"},
    })

    binance = ccxt.binance({
        "apiKey": Config.BINANCE_API_KEY,
        "secret": Config.BINANCE_API_SECRET,
        "enableRateLimit": True,
        "options": {"defaultType": "future"},  # perp futuros
    })

    return bybit, binance


# ─── Funding rate fetcher ────────────────────────────────────────────────────
def get_funding_rates(binance) -> dict:
    """Obtiene funding rates de Binance perp para todos los símbolos."""
    rates = {}
    try:
        # Trae todos los funding rates de una sola llamada
        markets = binance.fetch_funding_rates(Config.SYMBOLS)
        for symbol, data in markets.items():
            rate = data.get("fundingRate", 0)
            if rate is not None:
                rates[symbol] = float(rate) * 100  # en porcentaje
    except Exception as e:
        log.error(f"Error al obtener funding rates: {e}")
    return rates


def get_bybit_funding_rates(bybit) -> dict:
    """Obtiene funding rates de Bybit perp para comparar."""
    rates = {}
    try:
        bybit_perp = ccxt.bybit({
            "apiKey": Config.BYBIT_API_KEY,
            "secret": Config.BYBIT_API_SECRET,
            "enableRateLimit": True,
            "options": {"defaultType": "linear"},
        })
        markets = bybit_perp.fetch_funding_rates(Config.SYMBOLS)
        for symbol, data in markets.items():
            rate = data.get("fundingRate", 0)
            if rate is not None:
                rates[symbol] = float(rate) * 100
    except Exception as e:
        log.error(f"Error al obtener funding rates Bybit: {e}")
    return rates


# ─── Position manager ────────────────────────────────────────────────────────
class PositionManager:
    def __init__(self):
        self.positions = self._load_positions()

    def _load_positions(self) -> list:
        try:
            with open("data/positions.json") as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def _save_positions(self):
        os.makedirs("data", exist_ok=True)
        with open("data/positions.json", "w") as f:
            json.dump(self.positions, f, indent=2)

    def add(self, position: dict):
        self.positions.append(position)
        self._save_positions()
        log.info(f"Posición abierta: {position['symbol']} — ${position['capital']} USDT")

    def remove(self, symbol: str) -> Optional[dict]:
        for i, p in enumerate(self.positions):
            if p["symbol"] == symbol:
                pos = self.positions.pop(i)
                self._save_positions()
                return pos
        return None

    def get(self, symbol: str) -> Optional[dict]:
        return next((p for p in self.positions if p["symbol"] == symbol), None)

    def count(self) -> int:
        return len(self.positions)

    def symbols(self) -> list:
        return [p["symbol"] for p in self.positions]


# ─── Trade logger ─────────────────────────────────────────────────────────────
class TradeLogger:
    def __init__(self):
        os.makedirs("data", exist_ok=True)
        self.path = "data/trades.json"
        self.trades = self._load()

    def _load(self) -> list:
        try:
            with open(self.path) as f:
                return json.load(f)
        except FileNotFoundError:
            return []

    def _save(self):
        with open(self.path, "w") as f:
            json.dump(self.trades, f, indent=2)

    def log_open(self, symbol, capital, rate, spot_price, mode):
        trade = {
            "id": int(time.time()),
            "symbol": symbol,
            "capital": capital,
            "rate_at_open": rate,
            "spot_price": spot_price,
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
        closed = [t for t in self.trades if t["status"] == "closed"]
        total_pnl = sum(t["pnl_net"] or 0 for t in closed)
        total_funding = sum(t["funding_collected"] for t in closed)
        return {
            "total_trades": len(closed),
            "total_pnl": round(total_pnl, 4),
            "total_funding": round(total_funding, 4),
            "open_positions": len([t for t in self.trades if t["status"] == "open"]),
        }


# ─── Core bot logic ──────────────────────────────────────────────────────────
class FundingBot:
    def __init__(self):
        self.bybit, self.binance = init_exchanges()
        self.pm = PositionManager()
        self.tl = TradeLogger()
        mode = "PAPER TRADING" if Config.PAPER_TRADING else "REAL MONEY"
        log.info(f"Bot iniciado — Modo: {mode}")
        log.info(f"Capital por trade: ${Config.CAPITAL_PER_TRADE} | Rate mínimo: {Config.MIN_FUNDING_RATE}%")

    def get_spot_price(self, symbol: str) -> float:
        ticker = self.bybit.fetch_ticker(symbol)
        return float(ticker["last"])

    def open_position(self, symbol: str, rate: float):
        """Abre posición delta-neutral: spot en Bybit + short perp en Binance."""
        if self.pm.get(symbol):
            log.info(f"{symbol} ya tiene posición abierta, skip.")
            return

        if self.pm.count() >= Config.MAX_POSITIONS:
            log.warning(f"Máximo de posiciones ({Config.MAX_POSITIONS}) alcanzado.")
            return

        try:
            spot_price = self.get_spot_price(symbol)
            amount = Config.CAPITAL_PER_TRADE / spot_price

            if Config.PAPER_TRADING:
                log.info(f"[PAPER] Compra spot {symbol}: {amount:.6f} @ ${spot_price:.2f} en Bybit")
                log.info(f"[PAPER] Short perp {symbol}: {amount:.6f} @ ${spot_price:.2f} en Binance")
            else:
                # Compra spot en Bybit
                self.bybit.create_market_buy_order(symbol, amount)
                log.info(f"[REAL] Compra spot ejecutada: {symbol} {amount:.6f}")

                # Short perp en Binance
                binance_symbol = symbol.replace("/", "")
                self.binance.create_market_sell_order(binance_symbol, amount)
                log.info(f"[REAL] Short perp ejecutado: {symbol} {amount:.6f}")

            # Registrar
            position = {
                "symbol": symbol,
                "capital": Config.CAPITAL_PER_TRADE,
                "amount": amount,
                "entry_price": spot_price,
                "entry_rate": rate,
                "opened_at": datetime.utcnow().isoformat(),
                "funding_collected": 0,
            }
            self.pm.add(position)
            self.tl.log_open(
                symbol, Config.CAPITAL_PER_TRADE, rate, spot_price,
                "paper" if Config.PAPER_TRADING else "real"
            )

        except Exception as e:
            log.error(f"Error al abrir posición {symbol}: {e}")

    def close_position(self, symbol: str, reason: str = "manual"):
        """Cierra la posición delta-neutral."""
        pos = self.pm.get(symbol)
        if not pos:
            log.warning(f"No hay posición abierta para {symbol}")
            return

        try:
            if Config.PAPER_TRADING:
                log.info(f"[PAPER] Cierre spot {symbol}: venta de {pos['amount']:.6f}")
                log.info(f"[PAPER] Cierre perp {symbol}: compra (cierre short) de {pos['amount']:.6f}")
            else:
                # Venta spot en Bybit
                self.bybit.create_market_sell_order(symbol, pos["amount"])
                log.info(f"[REAL] Venta spot ejecutada: {symbol}")

                # Cierre short perp en Binance
                binance_symbol = symbol.replace("/", "")
                self.binance.create_market_buy_order(binance_symbol, pos["amount"])
                log.info(f"[REAL] Short perp cerrado: {symbol}")

            # Fee estimada: 0.1% entrada + 0.1% salida
            fees = Config.CAPITAL_PER_TRADE * 0.002
            pnl_net = pos["funding_collected"] - fees

            self.tl.log_close(symbol, pos["funding_collected"], pnl_net)
            self.pm.remove(symbol)

            log.info(
                f"Posición cerrada: {symbol} | "
                f"Funding: ${pos['funding_collected']:.4f} | "
                f"PnL neto: ${pnl_net:.4f} | "
                f"Razón: {reason}"
            )

        except Exception as e:
            log.error(f"Error al cerrar posición {symbol}: {e}")

    def update_funding_collected(self, symbol: str, rate: float):
        """Acumula el funding cobrado en cada ciclo de 8hs."""
        pos = self.pm.get(symbol)
        if pos:
            earned = pos["capital"] * (rate / 100)
            pos["funding_collected"] = pos.get("funding_collected", 0) + earned
            self.pm._save_positions()
            log.info(f"Funding cobrado {symbol}: +${earned:.4f} (total: ${pos['funding_collected']:.4f})")

    def run_cycle(self):
        """Ciclo principal: evalúa rates, abre/mantiene/cierra posiciones."""
        log.info("─" * 60)
        log.info("Iniciando ciclo de evaluación...")

        binance_rates = get_funding_rates(self.binance)
        bybit_rates   = get_bybit_funding_rates(self.bybit)

        if not binance_rates:
            log.warning("No se pudieron obtener funding rates, reintentando en el próximo ciclo.")
            return

        # Mostrar tabla de rates
        log.info(f"{'Par':<12} {'Bybit':>8} {'Binance':>8} {'Avg':>8} {'Estado'}")
        log.info("-" * 55)
        opportunities = []

        for sym in Config.SYMBOLS:
            b_rate = bybit_rates.get(sym, 0)
            bn_rate = binance_rates.get(sym, 0)
            avg = (b_rate + bn_rate) / 2
            already_open = sym in self.pm.symbols()
            status = "ABIERTA" if already_open else ("✓ OPORTUNIDAD" if avg >= Config.MIN_FUNDING_RATE else "—")
            log.info(f"{sym:<12} {b_rate:>7.4f}% {bn_rate:>7.4f}% {avg:>7.4f}%  {status}")

            if avg >= Config.MIN_FUNDING_RATE and not already_open:
                opportunities.append((sym, avg))

        # Actualizar funding de posiciones abiertas
        for sym in self.pm.symbols():
            rate = binance_rates.get(sym, 0)
            if rate > 0:
                self.update_funding_collected(sym, rate)
            elif rate < 0:
                # Rate negativo: pagamos nosotros → cerrar
                log.warning(f"{sym}: rate negativo ({rate:.4f}%), cerrando posición.")
                self.close_position(sym, reason="rate_negativo")

        # Abrir nuevas posiciones por orden de rentabilidad
        opportunities.sort(key=lambda x: x[1], reverse=True)
        for sym, rate in opportunities:
            if self.pm.count() < Config.MAX_POSITIONS:
                log.info(f"Abriendo posición: {sym} (rate: {rate:.4f}%)")
                self.open_position(sym, rate)

        # Resumen
        summary = self.tl.summary()
        log.info("─" * 60)
        log.info(
            f"RESUMEN | Posiciones abiertas: {self.pm.count()} | "
            f"Trades cerrados: {summary['total_trades']} | "
            f"PnL total: ${summary['total_pnl']}"
        )

    def run(self):
        """Loop principal."""
        log.info("=" * 60)
        log.info("  FUNDING RATE ARBITRAGE BOT — Bybit + Binance")
        log.info("=" * 60)

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

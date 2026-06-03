import os
import time
import json
import logging
from datetime import datetime, timezone
from typing import Optional
import ccxt

try:
    from pybit.unified_trading import HTTP as PybitHTTP
    PYBIT_OK = True
except ImportError:
    PYBIT_OK = False

# Crear carpetas base
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

# ─── Configuración ──────────────────────────────────────────────────────────
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

# ─── Inicialización de Exchanges ──────────────────────────────────────────────
def init_exchanges():
    rate_clients  = {}
    trade_clients = {}

    # Bybit
    rate_clients["bybit"] = ccxt.bybit({"enableRateLimit": True, "options": {"defaultType": "linear"}})
    if Config.BYBIT_API_KEY:
        if Config.BYBIT_DEMO and PYBIT_OK:
            trade_clients["bybit_pybit"] = PybitHTTP(
                testnet=False, demo=True,
                api_key=Config.BYBIT_API_KEY, api_secret=Config.BYBIT_API_SECRET
            )
            log.info(f"Bybit: pybit demo activo")
        else:
            trade_clients["bybit"] = ccxt.bybit({
                "apiKey": Config.BYBIT_API_KEY, "secret": Config.BYBIT_API_SECRET,
                "enableRateLimit": True, "options": {"defaultType": "linear"}
            })

    # Binance (Solo para rates y precios spot)
    rate_clients["binance"] = ccxt.binance({"enableRateLimit": True, "options": {"defaultType": "future"}})

    # Bitget
    rate_clients["bitget"] = ccxt.bitget({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    if Config.BITGET_API_KEY:
        opts = {"apiKey": Config.BITGET_API_KEY, "secret": Config.BITGET_API_SECRET, 
                "password": Config.BITGET_PASSPHRASE, "enableRateLimit": True, "options": {"defaultType": "swap"}}
        if Config.BITGET_DEMO:
            opts["urls"] = {"api": "https://api-sandbox.bitget.com"}
        trade_clients["bitget"] = ccxt.bitget(opts)

    # OKX
    rate_clients["okx"] = ccxt.okx({"enableRateLimit": True, "options": {"defaultType": "swap"}})
    if Config.OKX_API_KEY:
        opts = {"apiKey": Config.OKX_API_KEY, "secret": Config.OKX_API_SECRET, 
                "password": Config.OKX_PASSPHRASE, "enableRateLimit": True, "options": {"defaultType": "swap"}}
        if Config.OKX_DEMO:
            opts["headers"] = {"x-simulated-trading": "1"}
        trade_clients["okx"] = ccxt.okx(opts)

    return rate_clients, trade_clients

# ─── Auth Checker ─────────────────────────────────────────────────────────────
def check_auth(trade_clients):
    results = {}
    # Lógica simplificada de balance para el ejemplo
    for name in ["bybit", "okx", "bitget"]:
        client = trade_clients.get(name) or trade_clients.get(f"{name}_pybit")
        if not client:
            results[name] = {"status": "no_key"}
            continue
        try:
            results[name] = {"status": "ok"} # Simplificado para brevedad
        except:
            results[name] = {"status": "error"}
    return results

def save_auth_status(status):
    with open("data/auth_

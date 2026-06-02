# Funding Rate Arbitrage Bot
### Bybit (spot) + Binance (perp) — delta neutral

---

## ¿Qué hace este bot?

Cada hora revisa el funding rate de 10 pares cripto en Bybit y Binance.
Cuando el rate supera el umbral configurado, abre una posición delta-neutral:
- Compra el activo en **spot en Bybit**
- Abre un **short perpetuo en Binance** por el mismo monto

El resultado es una posición que no tiene exposición direccional al precio
pero cobra el funding rate cada 8 horas.

---

## Configuración inicial

### 1. Clonar y preparar

```bash
git clone <tu-repo>
cd funding-bot
cp .env.example .env
```

### 2. Completar el .env con tus API keys

```
BYBIT_API_KEY=...
BYBIT_API_SECRET=...
BINANCE_API_KEY=...
BINANCE_API_SECRET=...
PAPER_TRADING=true      ← empezar siempre en true
CAPITAL_PER_TRADE=500
MAX_POSITIONS=3
MIN_FUNDING_RATE=0.02
```

### 3. Crear las API keys en los exchanges

**Bybit:**
1. Perfil → Gestión de API → Crear nueva clave
2. Permisos necesarios: `Spot Trading` (lectura + escritura)
3. NO habilitar retiros
4. Guardar IP de Railway si querés más seguridad

**Binance:**
1. Cuenta → Seguridad → Gestión de API
2. Permisos: `Enable Futures` (lectura + escritura)
3. NO habilitar retiros

---

## Correr en local (para probar)

```bash
pip install -r requirements.txt
python bot.py
```

---

## Deploy en Railway

### Opción A — Desde GitHub (recomendado)

1. Subí el proyecto a GitHub (sin el `.env`)
2. Entrá a [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Seleccioná tu repo
4. En el panel de Railway: **Variables** → agregar todas las del `.env`
5. Railway detecta el `Procfile` y arranca automáticamente

### Opción B — Railway CLI

```bash
npm install -g @railway/cli
railway login
railway init
railway up
railway variables set BYBIT_API_KEY=... BYBIT_API_SECRET=... (etc)
```

---

## Parámetros ajustables

| Variable | Default | Descripción |
|---|---|---|
| `PAPER_TRADING` | `true` | Modo simulación sin dinero real |
| `MIN_FUNDING_RATE` | `0.02` | Rate mínimo (%) para entrar |
| `CAPITAL_PER_TRADE` | `500` | USDT por operación |
| `MAX_POSITIONS` | `3` | Máximo posiciones simultáneas |
| `CHECK_INTERVAL` | `3600` | Segundos entre ciclos (1 hora) |

---

## Flujo recomendado

```
Semana 1-2: PAPER_TRADING=true
   → Verificar que el bot encuentra oportunidades
   → Revisar logs diariamente
   → Calcular rentabilidad simulada

Semana 3-4: Cuenta demo de Bybit
   → Bybit tiene cuentas demo con fondos virtuales
   → Cambiar endpoint a testnet en bot.py

Mes 2+: PAPER_TRADING=false con capital real
   → Empezar con CAPITAL_PER_TRADE bajo ($100-200)
   → Escalar gradualmente
```

---

## Archivos de datos

- `data/positions.json` — posiciones abiertas actualmente
- `data/trades.json` — historial completo de operaciones
- `logs/bot.log` — log detallado de cada ciclo

---

## Riesgos a tener en cuenta

1. **Rate negativo**: si el rate se vuelve negativo, pagás en lugar de cobrar.
   El bot cierra la posición automáticamente en ese caso.

2. **Desincronización de precios**: si el precio se mueve mucho entre la
   compra spot y la apertura del short, podés entrar con slippage.

3. **Fees**: cada apertura y cierre cuesta ~0.1% en cada exchange.
   Con $500, eso son ~$2 de fees por operación — el funding debe superarlo.

4. **Liquidez**: con $500 por trade los pares principales tienen liquidez
   más que suficiente. No usar pares de baja capitalización.

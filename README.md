# BTC-MST — BTC Microstructure Trading Terminal

Automated BTC/USDT scalp trading system. Reads Binance order-flow in real time, generates microstructure signals tuned for a $100 TP / $30 SL setup (R:R 3.33:1), gates execution through a Claude AI batch analysis that sets directional bias, and executes on Exness via MetaTrader 5. AI monitors open trades for weakness and dynamically adjusts confidence thresholds based on session performance.

---

## What It Does

```
Binance WebSocket
  → aggTrade + depth20 + bookTicker
  → compute CVD, velocity (1s/3s/5s/10s), imbalance, sweep/absorption
  → Signal Engine (6 signal types — BTC $100/$30 tuning)
  → Signal batch → Claude AI (every 6 signals or 60s)
        → sets BIAS: LONG | SHORT | BOTH | PAUSE
        → assesses R:R favorability
        → adjusts confidence threshold
  → Bias gate (signal direction must match AI bias)
  → MT5 / Exness order — 1 BTC lot, SL=$30, TP=$100
  → Position monitor (P&L, SL/TP, 5min max hold)
  → Claude AI weakness check every 3s (EXIT / HOLD)
  → Claude AI post-trade review (R:R outcome + threshold update)
```

---

## Trading Parameters

| Parameter | Value |
|-----------|-------|
| Instrument | BTC/USDT (Binance) → BTCUSDm (Exness MT5) |
| Lot size | 1 BTC |
| Take profit | $100 price movement |
| Stop loss | $30 price movement |
| R:R ratio | 3.33 : 1 |
| Max hold time | 5 minutes (hard exit) |
| Max simultaneous positions | 1 |
| Min signal confidence | 0.70 |
| Global signal cooldown | 10s |
| Per-type signal cooldown | 20s |

---

## Signal Engine — Tuned for $100 TP / $30 SL

The $30 SL is tight for BTC — normal noise can easily hit it. Every signal requires **all four time windows (1s, 3s, 5s, 10s) to agree on direction** before firing. This eliminates most false entries that would get stopped out before the $100 target.

### Signal Types

| Signal | Trigger |
|--------|---------|
| `LONG_CONTINUATION` | All 4 windows net-positive + acceleration > 0 + aggression > 0.68 + cont_prob > 0.55. Uses 10s delta for trend conviction. |
| `SHORT_CONTINUATION` | Mirror — all 4 windows net-negative + acc < 0 + cont_prob < 0.45. |
| `SWEEP_REVERSAL_LONG` | Sell sweep (vel ≥ 1.5× min) exhausted + velocity flipping up + imbalance > 0.40 + net_1s positive. |
| `SWEEP_REVERSAL_SHORT` | Mirror — buy sweep exhausted + velocity flipping down. |
| `MOMENTUM_EXHAUSTION` | Velocity peak ≥ 3× threshold, then collapses to < 25% of peak within 15s + reversal signs in order flow. Catches post-big-move reversals which on BTC are often $100+. |
| `ABSORPTION_REVERSAL` | Large one-sided flow absorbed (price doesn't move) + directional flip: net_1s reverses + imbalance > 0.25 + acceleration turning. |

### Confidence Formula (LONG/SHORT CONTINUATION)

```
confidence = 0.35 × velocity_score
           + 0.25 × 10s_delta_score     ← trend conviction
           + 0.20 × aggression_score
           + 0.20 × continuation_prob   ← microstructure says move will continue
```

Minimum confidence to fire: **0.70** (vs. 0.65 previously).

### Why This Catches $100 Moves

- Multi-window alignment filters $30 noise — a trend present across 1s–10s is structural, not a spike
- `continuation_prob` weights toward moves with proven continuation character
- `MOMENTUM_EXHAUSTION` specifically targets post-big-move reversals (BTC frequently moves $200–500 on exhaustion)
- Higher per-type cooldown (20s) prevents repeat signals during choppy follow-through

---

## AI System — Batch Mode

AI does **not** validate individual signals. Instead it operates in batches to reduce latency and API cost while providing more context-aware decisions.

### AI Roles (Claude Sonnet 4.6)

| Role | Trigger | Output |
|------|---------|--------|
| **Batch analyzer** | Every 6 new signals OR every 60s | `BIAS: LONG\|SHORT\|BOTH\|PAUSE` + R:R assessment + threshold |
| **Market analyst** | Every 30s (background) | Regime + bias + R:R verdict + threshold |
| **Weakness monitor** | Every 3s while position open | `EXIT\|HOLD` — heuristics first, AI only if hold > 60s and profit > 0 |
| **Trade reviewer** | After every close | `RR_VERDICT: FAVORABLE\|UNFAVORABLE\|NEUTRAL` + threshold adjustment |

### Execution Bias

The AI sets a directional bias after each batch analysis:

| Bias | Effect |
|------|--------|
| `BOTH` | All signals execute (default) |
| `LONG` | Only LONG signals execute; SHORT signals skipped |
| `SHORT` | Only SHORT signals execute; LONG signals skipped |
| `PAUSE` | No signals execute — AI sees unfavorable conditions |

Bias can also be overridden manually via `POST /api/ai/bias`.

### Dynamic Confidence Threshold

- Starts at **0.70**, adjusts range **0.55–0.90**
- Updated by both batch analysis and post-trade review
- Tightens after losses (harder to fire), loosens after wins
- Displayed in header bar as `thr=X.XX`

---

## Stack

| Layer | Tech |
|-------|------|
| Backend | Python 3.12, FastAPI, asyncio |
| Data feed | Binance public WebSocket (no API key needed) |
| AI | Anthropic Claude Sonnet 4.6 |
| Execution | MetaTrader5 Python API → Exness MT5 |
| Database | SQLite (aiosqlite) |
| Frontend | React 18, TypeScript, Vite, Zustand |
| Transport | WebSocket (FastAPI → browser) |

---

## Project Structure

```
binance_exness/
├── backend/
│   ├── main.py                          # FastAPI app, signal pipeline, bias gate
│   ├── config.py                        # All settings (env-driven)
│   ├── websocket_gateway.py             # WS broadcast to frontend
│   ├── services/
│   │   ├── binance_stream_service.py    # Binance WS, microstructure metrics
│   │   ├── signal_engine_service.py     # 6 signal types, BTC $100/$30 tuning
│   │   ├── ai_analysis_service.py       # Batch analysis, weakness, trade review
│   │   ├── mt5_execution_service.py     # MT5 connect, open/close, SL/TP monitor
│   │   └── analytics_service.py        # Session P&L metrics
│   └── database/
│       └── db.py                        # SQLite schema, trade persistence
├── frontend/
│   └── src/
│       ├── App.tsx                      # Full-screen terminal UI
│       ├── hooks/useWebSocket.ts        # WS connection, message dispatch
│       └── stores/
│           ├── marketStore.ts           # Price, signals, market state
│           ├── mt5Store.ts              # Open positions, closed trade history
│           ├── aiStore.ts               # AI analysis feed
│           └── systemStore.ts           # Connection status
├── start_backend.ps1
├── start_frontend.ps1
└── README.md
```

---

## Setup

### Requirements
- Windows (MT5 is Windows-only)
- Python 3.12
- Node.js 18+
- MetaTrader 5 terminal installed and logged into Exness
- Anthropic API key

### 1. Backend

```powershell
cd backend
python -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

Create `backend/.env`:

```env
ANTHROPIC_API_KEY=sk-ant-...

# MT5 / Exness credentials
MT5_LOGIN=12345678
MT5_PASSWORD=your_password
MT5_SERVER=Exness-MT5Real8
MT5_SYMBOL=BTCUSDm
# MT5_TERMINAL_PATH=C:\Program Files\Exness MT5 Terminal\terminal64.exe
```

> **Symbol name:** If connection fails with `symbol_select failed`, the system auto-detects all BTC symbols on your account and lists them in the UI. Copy the correct name into `MT5_SYMBOL` and restart.

```powershell
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
```

### 2. Frontend

```powershell
cd frontend
npm install
npm run dev
```

Open `http://localhost:5173`

Or use the scripts from project root:
```powershell
.\start_backend.ps1   # terminal 1
.\start_frontend.ps1  # terminal 2
```

---

## Usage

1. **START** — connects Binance WebSocket, begins market data and signal flow
2. **CONNECT MT5** — logs into Exness terminal (requires `.env` credentials)
3. **LIVE ON** — arms live trading (real money at risk)
4. **AUTO ON** — approved signals execute automatically based on AI bias
5. **BUY / SELL** — manual execution (requires LIVE ON)
6. Watch **AI BIAS** in the header — `LONG/SHORT/BOTH/PAUSE` shown in color
7. Watch **AI FEED** panel for R:R assessments and batch analysis results

### MT5 AutoTrading error (retcode 10027)

MT5 terminal has AutoTrading globally disabled. In MT5 toolbar, click **"Algo Trading"** until it turns green. This is a terminal-level setting separate from the LIVE/AUTO toggles in this app.

---

## Microstructure Metrics

| Metric | Description |
|--------|-------------|
| CVD | Cumulative Volume Delta — running total of buyer minus seller aggression |
| Velocity | USD notional per second — 1s, 3s, 5s, 10s rolling windows |
| Net Delta | Buyer minus seller delta per window |
| Acceleration | Rate of change of velocity (1s) — detects momentum shifts |
| Imbalance | Bid/ask order book size ratio (positive = bid-heavy) |
| Aggression Score | Market order aggression vs passive limit orders |
| Sweep Detected | Large market order consumed multiple price levels |
| Absorption Detected | Heavy one-sided flow not moving price — other side absorbing |
| Continuation Prob | Microstructure probability that current move continues |

---

## API Endpoints

```
POST /api/flow/start            start Binance stream + signal engine
POST /api/flow/stop             stop stream
GET  /api/status                all connection/AI status + current bias
GET  /api/market                current market microstructure state

POST /api/mt5/connect           connect to Exness MT5
POST /api/mt5/disconnect
POST /api/mt5/enable            toggle live trading (real money gate)
POST /api/mt5/auto-execute      toggle automatic signal execution
GET  /api/mt5/account           balance, equity, margin
GET  /api/mt5/positions         open positions
POST /api/mt5/trade/open        manual open  { side, lot_size }
POST /api/mt5/trade/{t}/close   close one position by ticket
POST /api/mt5/trade/close-all   close all positions

GET  /api/signals               recent signals (limit param)
GET  /api/analytics             session P&L metrics

GET  /api/ai/threshold          current confidence threshold
POST /api/ai/threshold          set threshold  ?value=0.72
GET  /api/ai/bias               current bias + reason
POST /api/ai/bias               override bias  ?bias=LONG
POST /api/ai/analyze            trigger market analysis now

GET  /api/config                lot_size, tp, sl, rr_ratio, batch_size
```

---

## Key Design Decisions

- **Batch AI, not per-signal.** Per-signal AI adds 1–3s latency to every trade decision and misses context across multiple signals. Batch analysis sees patterns across 5–6 signals and sets a directional bias — more intelligent and faster at execution time.
- **AI bias as execution gate.** Instead of EXECUTE/SKIP per signal, AI sets `LONG/SHORT/BOTH/PAUSE`. A PAUSE from AI skips all signals; LONG skips SHORT signals. The bias persists until the next batch update.
- **R:R assessment in every AI call.** Every batch analysis and market analysis explicitly evaluates whether $100 TP / $30 SL is favorable given current volatility and momentum regime.
- **All-window alignment required.** 1s, 3s, 5s, and 10s net delta must all agree before firing a continuation signal. This single requirement eliminates most noise-stop entries.
- **One position at a time.** No pyramiding. New signals ignored while a position is open.
- **SL/TP on order.** Price levels set directly in the MT5 order request — survive backend restarts and connection drops.
- **Dynamic confidence threshold.** Starts at 0.70, adjusts 0.55–0.90 based on batch signal quality and post-trade R:R outcome.
- **MT5 in thread pool.** All blocking MT5 API calls run in `ThreadPoolExecutor` — never blocks the FastAPI event loop.
- **No charts, no noise.** Terminal UI: price, AI bias, last signal, open P&L, closed trade history, scrollable AI feed, controls.

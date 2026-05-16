"""
AI engine: Claude Sonnet 4.6.

Four roles:
1. analyze_signal_batch() — called after every N signals or every 60s.
   Reviews signal quality + R:R, sets execution bias (LONG/SHORT/BOTH/PAUSE).
2. check_trade_weakness()  — monitors open trade every 3s (EXIT/HOLD).
3. analyze_trade()         — post-trade review, adjusts confidence threshold.
4. _background_loop()      — market regime + R:R assessment every 30s.

No per-signal AI gate. AI operates in batches to reduce latency and API cost.
"""
import asyncio
import time
from typing import Callable, Optional
import anthropic
import structlog

from config import settings

log = structlog.get_logger(__name__)

# Late import to avoid circular dependency — risk_manager imports config only
def _get_regime_stats() -> str:
    try:
        from services.risk_manager import risk_manager
        stats = risk_manager.get_regime_stats()
        if not stats:
            return ""
        lines = [
            f"  {k}: {v['count']}T WR={v['win_rate']:.0%} PnL=${v['net_pnl']:.0f}"
            for k, v in list(stats.items())[-8:]
        ]
        return "\nSession regime performance:\n" + "\n".join(lines)
    except Exception:
        return ""

VALID_BIASES = {"LONG", "SHORT", "BOTH", "PAUSE"}


class AIAnalysisService:
    def __init__(self):
        self._client: Optional[anthropic.AsyncAnthropic] = None
        self._callbacks: list[Callable] = []
        self._running = False
        self._task: Optional[asyncio.Task] = None

        # Dynamic confidence threshold
        self.confidence_threshold: float = settings.min_confidence

        # Execution bias — set by batch/market analysis
        # BOTH = take any signal, LONG/SHORT = directional only, PAUSE = hold off
        self._current_bias: str = "BOTH"
        self._bias_reason: str = "AI not yet analyzed"

        # Signal batch accumulator
        self._signal_batch: list[dict] = []
        self._signals_since_last_batch: int = 0
        self._last_batch_time: float = 0.0

        # Context
        self._last_market: dict = {}
        self._recent_trades: list[dict] = []
        self._analysis_count = 0

        # Weakness check rate-limit — AI call at most once per 15s per position
        self._last_weakness_check: float = 0.0

        # Feature toggles (runtime-mutable from API)
        self.signals_enabled: bool = True   # signal batch + market analysis
        self.weakness_enabled: bool = True  # trade weakness monitor

        # Per-minute rate limit — prevents API spam during high-volatility bursts
        self._ai_call_times: list[float] = []  # timestamps of recent AI calls

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def current_bias(self) -> str:
        return self._current_bias

    @property
    def bias_reason(self) -> str:
        return self._bias_reason

    def subscribe(self, callback: Callable):
        self._callbacks.append(callback)

    def _rate_limit_ok(self) -> bool:
        """Return True and record call if under max_ai_calls_per_minute, else False."""
        now = time.time()
        cutoff = now - 60.0
        self._ai_call_times = [t for t in self._ai_call_times if t > cutoff]
        limit = getattr(settings, "max_ai_calls_per_minute", 15)
        if len(self._ai_call_times) >= limit:
            log.warning("AI rate limit hit",
                        calls_last_min=len(self._ai_call_times), limit=limit)
            return False
        self._ai_call_times.append(now)
        return True

    def update_context(self, market: dict, trades: list[dict], signals: list[dict]):
        self._last_market = market
        self._recent_trades = trades[-20:]

    def add_signal(self, signal: dict):
        """Feed every new signal into the batch accumulator."""
        if not self.signals_enabled:
            return
        self._signal_batch.append({
            "type": signal.get("signal_type"),
            "conf": round(signal.get("confidence", 0), 3),
            "price": signal.get("price", 0),
            "reason": (signal.get("trigger_reason") or "")[:60],
            "ts": signal.get("timestamp", time.time()),
        })
        # Keep batch bounded
        if len(self._signal_batch) > 50:
            self._signal_batch = self._signal_batch[-50:]
        self._signals_since_last_batch += 1
        if self._signals_since_last_batch >= settings.ai_batch_size:
            asyncio.create_task(self._run_batch_analysis())

    async def start(self):
        if not settings.anthropic_api_key:
            log.warning("No ANTHROPIC_API_KEY — AI disabled")
            return
        self._client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
        self._running = True
        self._task = asyncio.create_task(self._background_loop())
        log.info("AIAnalysisService started")

    async def stop(self):
        self._running = False
        if self._task:
            self._task.cancel()

    # ── Batch signal analysis ──────────────────────────────────────────────────

    async def _run_batch_analysis(self):
        """Analyze accumulated signals. Sets execution bias + R:R assessment."""
        if not self._client or not self._signal_batch:
            return
        if not self._rate_limit_ok():
            return

        self._signals_since_last_batch = 0
        self._last_batch_time = time.time()
        batch = self._signal_batch[-settings.ai_batch_size:]
        m = self._last_market

        rr_ratio = settings.tp_usd_per_lot / settings.sl_usd_per_lot

        sig_lines = "\n".join(
            f"  {i+1}. {s['type']} conf={s['conf']:.0%} "
            f"${s['price']:,.0f} — {s['reason']}"
            for i, s in enumerate(batch)
        )

        wins   = [t for t in self._recent_trades if t.get("profit", 0) > 0]
        losses = [t for t in self._recent_trades if t.get("profit", 0) <= 0
                  and t.get("status") == "CLOSED"]
        session_pnl = sum(t.get("profit", 0) for t in self._recent_trades
                          if t.get("status") == "CLOSED")

        prompt = (
            f"BTC/USDT ${m.get('price', 0):,.0f} | "
            f"CVD={m.get('cvd', 0):,.0f} imb={m.get('imbalance', 0):.2f} "
            f"agg={m.get('aggression_score', 0.5):.2f} | "
            f"vel5s={m.get('velocity', {}).get(5, 0):,.0f}/s "
            f"net5s={m.get('net_delta', {}).get(5, 0):,.0f} | "
            f"sweep={m.get('sweep_detected')} abs={m.get('absorption_detected')}\n\n"
            f"Last {len(batch)} signals:\n{sig_lines}\n\n"
            f"Session: {len(wins)}W / {len(losses)}L  net P&L=${session_pnl:.2f}\n"
            f"R:R setup: TP=${settings.tp_usd_per_lot} / SL=${settings.sl_usd_per_lot} = {rr_ratio:.2f}:1\n"
            f"Current bias: {self._current_bias} | threshold: {self.confidence_threshold:.2f}"
            + _get_regime_stats()
        )

        try:
            resp = await asyncio.wait_for(
                self._client.messages.create(
                    model=settings.ai_model,
                    max_tokens=200,
                    system=(
                        "You are a BTC/USDT scalp trade analyst. Review the signal batch and market.\n"
                        "Consider: signal direction consistency, R:R favorability, market regime, session P&L.\n"
                        "Respond ONLY in this exact format:\n"
                        "BIAS: <LONG|SHORT|BOTH|PAUSE>\n"
                        "RR: <one sentence — is current R:R favorable and why>\n"
                        "NOTE: <one sentence on dominant pattern in this batch>\n"
                        "THRESHOLD: <float 0.55-0.90>\n"
                        "No other text."
                    ),
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=10.0,
            )
            text = resp.content[0].text.strip()
            self._analysis_count += 1

            for line in text.split("\n"):
                if line.startswith("BIAS:"):
                    b = line.split(":", 1)[1].strip().upper()
                    if b in VALID_BIASES:
                        old = self._current_bias
                        self._current_bias = b
                        if old != b:
                            log.info("AI bias changed", old=old, new=b)
                elif line.startswith("NOTE:"):
                    self._bias_reason = line.split(":", 1)[1].strip()
                elif line.startswith("THRESHOLD:"):
                    try:
                        t = float(line.split(":", 1)[1].strip())
                        self.confidence_threshold = max(0.55, min(0.90, t))
                    except Exception:
                        pass

            await self._emit({
                "type": "ai_analysis",
                "content": text,
                "analysis_type": "SIGNAL_BATCH",
                "bias": self._current_bias,
                "threshold": self.confidence_threshold,
                "signals_reviewed": len(batch),
                "rr_ratio": rr_ratio,
                "analysis_count": self._analysis_count,
                "timestamp": time.time(),
            })
            log.info("AI batch done", bias=self._current_bias, threshold=self.confidence_threshold,
                     signals=len(batch))

        except asyncio.TimeoutError:
            log.warning("AI batch analysis timeout — bias unchanged")
        except Exception as e:
            log.error("AI batch analysis error", error=str(e))

    # ── Trade weakness check ───────────────────────────────────────────────────

    async def check_trade_weakness(self, trade: dict, market: dict) -> dict:
        """Check open BTC trade for weakness. Heuristics first, AI only when needed."""
        if not self.weakness_enabled:
            return {"exit_now": False, "reason": "weakness monitor disabled"}
        if not self._client:
            return {"exit_now": False, "reason": "AI disabled"}

        side   = trade.get("side", "BUY")
        profit = trade.get("profit", 0.0)
        hold   = trade.get("hold_seconds", 0.0)
        vel5   = market.get("velocity", {}).get(5, 0.0)
        net5   = market.get("net_delta", {}).get(5, 0.0)
        agg    = market.get("aggression_score", 0.5)

        # BTC heuristics (thresholds ~10x ETH)
        if side == "BUY" and vel5 < -150000 and net5 < -400000:
            return {"exit_now": True, "reason": "Strong reversal vs BUY"}
        if side == "SELL" and vel5 > 150000 and net5 > 400000:
            return {"exit_now": True, "reason": "Strong reversal vs SELL"}

        # AI only when hold > 60s and profit > 0, and not called in last 15s
        if hold < 60 or profit <= 0:
            return {"exit_now": False, "reason": ""}

        now = time.time()
        if now - self._last_weakness_check < 15.0:
            return {"exit_now": False, "reason": ""}
        if not self._rate_limit_ok():
            return {"exit_now": False, "reason": ""}
        self._last_weakness_check = now

        prompt = (
            f"Open {side} BTC | profit=${profit:.2f} hold={hold:.0f}s | "
            f"vel5s={vel5:,.0f}/s net5s={net5:,.0f} agg={agg:.2f} "
            f"sweep={market.get('sweep_detected')} abs={market.get('absorption_detected')} | "
            f"TP=${settings.tp_usd_per_lot} SL=${settings.sl_usd_per_lot}"
        )

        try:
            resp = await asyncio.wait_for(
                self._client.messages.create(
                    model=settings.ai_model,
                    max_tokens=60,
                    system=(
                        "Monitor open BTC scalp trade for weakness. "
                        "Respond ONLY: EXIT|HOLD\nReason: <10 words max>"
                    ),
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=2.0,
            )
            text = resp.content[0].text.strip()
            exit_now = text.upper().startswith("EXIT")
            reason = text.split("\n")[1].replace("Reason:", "").strip() if "\n" in text else ""
            return {"exit_now": exit_now, "reason": reason}
        except Exception:
            return {"exit_now": False, "reason": ""}

    # ── Post-trade analysis ────────────────────────────────────────────────────

    async def analyze_trade(self, trade: dict, market: dict):
        """After trade closes — assess R:R outcome and adjust threshold."""
        if not self._client:
            return
        if not self._rate_limit_ok():
            return

        wins   = [t for t in self._recent_trades if t.get("status") == "CLOSED" and t.get("profit", 0) > 0]
        losses = [t for t in self._recent_trades if t.get("status") == "CLOSED" and t.get("profit", 0) <= 0]
        total  = len(wins) + len(losses)
        win_rate = len(wins) / total if total > 0 else 0.5
        rr_ratio = settings.tp_usd_per_lot / settings.sl_usd_per_lot

        prompt = (
            f"Closed BTC {trade.get('side')} @ ${trade.get('entry_price', 0):,.0f} → "
            f"${trade.get('exit_price', trade.get('current_price', 0)):,.0f} "
            f"profit=${trade.get('profit', 0):.2f} reason={trade.get('exit_reason', '')} | "
            f"R:R setup={rr_ratio:.2f}:1 (TP=${settings.tp_usd_per_lot} SL=${settings.sl_usd_per_lot}) | "
            f"Session: {total} trades win_rate={win_rate:.1%} "
            f"net=${sum(t.get('profit',0) for t in wins+losses):.2f}"
        )

        try:
            resp = await asyncio.wait_for(
                self._client.messages.create(
                    model=settings.ai_model,
                    max_tokens=180,
                    system=(
                        "Analyze this BTC scalp trade outcome vs expected R:R.\n"
                        "Respond in this exact format:\n"
                        "THRESHOLD: <float 0.55-0.90>\n"
                        "RR_VERDICT: <FAVORABLE|UNFAVORABLE|NEUTRAL>\n"
                        "Analysis: <2 sentences — R:R outcome vs expectation and what to adjust>\n"
                        "No other text."
                    ),
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=6.0,
            )
            text = resp.content[0].text.strip()

            for line in text.split("\n"):
                if line.startswith("THRESHOLD:"):
                    try:
                        new_t = float(line.split(":", 1)[1].strip())
                        old = self.confidence_threshold
                        self.confidence_threshold = max(0.55, min(0.90, new_t))
                        log.info("AI adjusted threshold", old=old, new=self.confidence_threshold)
                    except Exception:
                        pass

            await self._emit({
                "type": "ai_analysis",
                "content": text,
                "analysis_type": "TRADE_REVIEW",
                "threshold": self.confidence_threshold,
                "rr_ratio": rr_ratio,
                "trade_id": trade.get("ticket") or trade.get("id"),
                "timestamp": time.time(),
            })
        except Exception as e:
            log.error("Trade analysis error", error=str(e))

    # ── Background loop ────────────────────────────────────────────────────────

    async def _background_loop(self):
        while self._running:
            try:
                await asyncio.sleep(settings.ai_analysis_interval)
                if not self._last_market or not self.signals_enabled:
                    continue
                # Run batch analysis if signals accumulated but batch_size not hit yet
                secs_since = time.time() - self._last_batch_time
                if self._signal_batch and secs_since >= settings.ai_batch_interval:
                    await self._run_batch_analysis()
                else:
                    await self._run_market_analysis()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("AI background loop error", error=str(e))
                await asyncio.sleep(5)

    async def _run_market_analysis(self):
        """Market regime + R:R assessment when no signal batch is ready."""
        m = self._last_market
        if not m:
            return
        if not self._rate_limit_ok():
            return

        vel = m.get("velocity", {})
        net = m.get("net_delta", {})
        rr_ratio = settings.tp_usd_per_lot / settings.sl_usd_per_lot
        closed = [t for t in self._recent_trades if t.get("status") == "CLOSED"]
        recent_pnl = sum(t.get("profit", 0) for t in closed[-5:])

        prompt = (
            f"BTC/USDT ${m.get('price', 0):,.0f} | "
            f"CVD={m.get('cvd', 0):,.0f} imb={m.get('imbalance', 0):.2f} "
            f"agg={m.get('aggression_score', 0.5):.2f} | "
            f"vel1s={vel.get(1, 0):,.0f} vel5s={vel.get(5, 0):,.0f} vel10s={vel.get(10, 0):,.0f} | "
            f"net5s={net.get(5, 0):,.0f} net10s={net.get(10, 0):,.0f} | "
            f"sweep={m.get('sweep_detected')} abs={m.get('absorption_detected')} | "
            f"last5_pnl=${recent_pnl:.2f} | bias={self._current_bias} | "
            f"threshold={self.confidence_threshold:.2f} | "
            f"R:R={rr_ratio:.2f}:1 (TP=${settings.tp_usd_per_lot} SL=${settings.sl_usd_per_lot})"
            + _get_regime_stats()
        )

        try:
            resp = await asyncio.wait_for(
                self._client.messages.create(
                    model=settings.ai_model,
                    max_tokens=220,
                    system=(
                        "You are a BTC/USDT scalp trading AI. Analyze market and R:R conditions.\n"
                        "Output format:\n"
                        "REGIME: <TRENDING_UP|TRENDING_DOWN|CHOPPY|ACCUMULATING>\n"
                        "BIAS: <LONG|SHORT|BOTH|PAUSE>\n"
                        "RR: <one sentence — is TP/SL ratio favorable in current conditions>\n"
                        "THRESHOLD: <float 0.55-0.90>\n"
                        "Note: <one sentence on what signals to prioritize>\n"
                        "No other text."
                    ),
                    messages=[{"role": "user", "content": prompt}],
                ),
                timeout=10.0,
            )
            text = resp.content[0].text.strip()
            self._analysis_count += 1

            for line in text.split("\n"):
                if line.startswith("BIAS:"):
                    b = line.split(":", 1)[1].strip().upper()
                    if b in VALID_BIASES:
                        self._current_bias = b
                elif line.startswith("NOTE:"):
                    self._bias_reason = line.split(":", 1)[1].strip()
                elif line.startswith("THRESHOLD:"):
                    try:
                        t = float(line.split(":", 1)[1].strip())
                        self.confidence_threshold = max(0.55, min(0.90, t))
                    except Exception:
                        pass

            await self._emit({
                "type": "ai_analysis",
                "content": text,
                "analysis_type": "MARKET",
                "bias": self._current_bias,
                "threshold": self.confidence_threshold,
                "rr_ratio": rr_ratio,
                "analysis_count": self._analysis_count,
                "timestamp": time.time(),
            })
        except asyncio.TimeoutError:
            log.warning("Background AI analysis timeout")
        except Exception as e:
            log.error("Background AI error", error=str(e))

    async def _emit(self, payload: dict):
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    cb(payload)
            except Exception as e:
                log.warning("AI callback error", error=str(e))


ai_service = AIAnalysisService()

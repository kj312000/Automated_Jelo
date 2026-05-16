"""
BTC/USDT signal engine — tuned for $100 TP / $30 SL (R:R 3.33:1).

Design philosophy for $30 SL:
  - $30 is tight for BTC — normal noise can easily hit it.
  - Only fire when ALL windows (1s, 3s, 5s, 10s) agree on direction.
  - Velocity must be strong enough that $100 continuation is plausible.
  - Continuation probability must be high (move already established).
  - Fewer, higher-quality signals beats many mediocre ones.
  - Per-type cooldown 20s, global cooldown 10s.

Signal types:
  LONG_CONTINUATION   — multi-window buyer dominance, acc positive
  SHORT_CONTINUATION  — multi-window seller dominance, acc negative
  SWEEP_REVERSAL_LONG  — sell sweep exhausted, buyers absorbing → long
  SWEEP_REVERSAL_SHORT — buy sweep exhausted, sellers absorbing → short
  MOMENTUM_EXHAUSTION  — velocity peak + collapse signals reversal
  ABSORPTION_REVERSAL  — large one-sided flow absorbed; price expected to reverse
"""
import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Callable, Optional
import structlog

from config import settings

log = structlog.get_logger(__name__)


class SignalType(str, Enum):
    LONG_CONTINUATION    = "LONG_CONTINUATION"
    SHORT_CONTINUATION   = "SHORT_CONTINUATION"
    SWEEP_REVERSAL_LONG  = "SWEEP_REVERSAL_LONG"
    SWEEP_REVERSAL_SHORT = "SWEEP_REVERSAL_SHORT"
    MOMENTUM_EXHAUSTION  = "MOMENTUM_EXHAUSTION"
    ABSORPTION_REVERSAL  = "ABSORPTION_REVERSAL"


@dataclass
class Signal:
    id: int
    signal_type: SignalType
    confidence: float
    continuation_prob: float
    velocity_score: float
    delta_score: float
    imbalance_score: float
    aggression_score: float
    price: float
    trigger_reason: str
    timestamp: float = field(default_factory=time.time)


class SignalEngineService:
    def __init__(self):
        self._paused = False
        self._running = False
        self._signal_id_counter = 0
        self._callbacks: list[Callable] = []
        self._last_signal_time: float = 0.0
        self._recent_signals: list[Signal] = []
        self._type_cooldowns: dict[str, float] = {}

        # Peak velocity tracking for MOMENTUM_EXHAUSTION
        self._vel_peak: float = 0.0
        self._vel_peak_side: str = ""   # "BUY" | "SELL"
        self._vel_peak_time: float = 0.0

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def is_paused(self) -> bool:
        return self._paused

    def subscribe(self, cb: Callable):
        self._callbacks.append(cb)

    def start(self):
        self._running = True
        log.info("SignalEngine started (BTC $100TP/$30SL tuning)")

    def stop(self):
        self._running = False
        log.info("SignalEngine stopped")

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    async def process(self, market: dict) -> Optional[Signal]:
        if not self._running or self._paused:
            return None

        now = time.time()
        if now - self._last_signal_time < settings.signal_cooldown_seconds:
            return None

        if not market.get("price"):
            return None

        self._update_velocity_peak(market, now)

        signal = self._evaluate(market, now)
        if signal:
            self._last_signal_time = now
            self._type_cooldowns[signal.signal_type] = now
            self._recent_signals.append(signal)
            if len(self._recent_signals) > 200:
                self._recent_signals.pop(0)
            await self._emit(signal)

        return signal

    def _type_on_cooldown(self, st: SignalType, now: float) -> bool:
        last = self._type_cooldowns.get(st, 0.0)
        return (now - last) < settings.signal_type_cooldown_seconds

    def _update_velocity_peak(self, m: dict, now: float):
        """Track rolling velocity peak for MOMENTUM_EXHAUSTION detection."""
        vel5 = m.get("velocity", {}).get(5, 0.0)
        abs_vel = abs(vel5)
        side = "BUY" if vel5 > 0 else "SELL"

        # Reset peak if side changed or peak is stale (>30s old)
        if self._vel_peak_side != side or (now - self._vel_peak_time) > 30.0:
            self._vel_peak = abs_vel
            self._vel_peak_side = side
            self._vel_peak_time = now
        elif abs_vel > self._vel_peak:
            self._vel_peak = abs_vel
            self._vel_peak_time = now

    def _evaluate(self, m: dict, now: float) -> Optional[Signal]:
        vel   = m.get("velocity", {})
        net   = m.get("net_delta", {})
        agg_b = m.get("agg_buy_delta", {})
        agg_s = m.get("agg_sell_delta", {})
        acc   = m.get("acceleration", {})

        imbalance  = m.get("imbalance", 0.0)
        aggression = m.get("aggression_score", 0.5)
        sweep      = m.get("sweep_detected", False)
        absorption = m.get("absorption_detected", False)
        cont_prob  = m.get("continuation_prob", 0.5)
        price      = m.get("price", 0.0)

        vel_1s  = vel.get(1,  0.0)
        vel_3s  = vel.get(3,  0.0)
        vel_5s  = vel.get(5,  0.0)
        vel_10s = vel.get(10, 0.0)
        net_1s  = net.get(1,  0.0)
        net_3s  = net.get(3,  0.0)
        net_5s  = net.get(5,  0.0)
        net_10s = net.get(10, 0.0)
        buy_5s  = agg_b.get(5, 0.0)
        sell_5s = agg_s.get(5, 0.0)
        total_5s = buy_5s + sell_5s
        acc_1s  = acc.get(1, 0.0)

        V  = settings.min_velocity_threshold   # 200K USD/s
        D  = settings.min_delta_threshold      # 600K USD
        MI = settings.min_imbalance_ratio      # 0.68
        MC = settings.min_confidence           # 0.70

        # ── LONG CONTINUATION ────────────────────────────────────────────────
        # All 4 windows positive + acceleration positive → trend is real and accelerating.
        # Needs strong enough velocity that a $100 continuation is plausible.
        if (
            not self._type_on_cooldown(SignalType.LONG_CONTINUATION, now)
            and net_1s > 0 and net_3s > 0 and net_5s > 0 and net_10s > 0  # all windows aligned
            and vel_5s > V
            and vel_10s > V * 0.6       # 10s trend also up (not just a spike)
            and acc_1s > 0              # still accelerating
            and aggression > MI
            and total_5s > D
            and cont_prob > 0.55        # microstructure says move will continue
        ):
            vel_score  = min(vel_5s / (V * 4), 1.0)
            delta_score = min(net_10s / (D * 2), 1.0)   # use 10s delta for conviction
            imb_score  = max(imbalance, 0.0)
            agg_score  = (aggression - 0.5) * 2

            # Confidence: velocity 35% + 10s delta 25% + aggression 20% + cont_prob 20%
            confidence = (
                0.35 * vel_score
                + 0.25 * delta_score
                + 0.20 * agg_score
                + 0.20 * ((cont_prob - 0.5) * 2)
            )
            confidence = max(0.0, min(1.0, confidence))

            if confidence >= MC:
                return Signal(
                    id=self._next_id(),
                    signal_type=SignalType.LONG_CONTINUATION,
                    confidence=confidence,
                    continuation_prob=cont_prob,
                    velocity_score=vel_score,
                    delta_score=delta_score,
                    imbalance_score=imb_score,
                    aggression_score=aggression,
                    price=price,
                    trigger_reason=(
                        f"All-window long: vel5={vel_5s:,.0f} vel10={vel_10s:,.0f} "
                        f"net10={net_10s:,.0f} agg={aggression:.2f} cont={cont_prob:.2f}"
                    ),
                )

        # ── SHORT CONTINUATION ───────────────────────────────────────────────
        if (
            not self._type_on_cooldown(SignalType.SHORT_CONTINUATION, now)
            and net_1s < 0 and net_3s < 0 and net_5s < 0 and net_10s < 0
            and vel_5s < -V
            and vel_10s < -V * 0.6
            and acc_1s < 0
            and aggression < (1 - MI)
            and total_5s > D
            and cont_prob < 0.45
        ):
            vel_score   = min(abs(vel_5s) / (V * 4), 1.0)
            delta_score = min(abs(net_10s) / (D * 2), 1.0)
            imb_score   = max(-imbalance, 0.0)
            seller_dom  = (1 - aggression - 0.5) * 2

            confidence = (
                0.35 * vel_score
                + 0.25 * delta_score
                + 0.20 * seller_dom
                + 0.20 * ((0.5 - cont_prob) * 2)
            )
            confidence = max(0.0, min(1.0, confidence))

            if confidence >= MC:
                return Signal(
                    id=self._next_id(),
                    signal_type=SignalType.SHORT_CONTINUATION,
                    confidence=confidence,
                    continuation_prob=1 - cont_prob,
                    velocity_score=vel_score,
                    delta_score=delta_score,
                    imbalance_score=imb_score,
                    aggression_score=aggression,
                    price=price,
                    trigger_reason=(
                        f"All-window short: vel5={vel_5s:,.0f} vel10={vel_10s:,.0f} "
                        f"net10={net_10s:,.0f} agg={aggression:.2f} cont={cont_prob:.2f}"
                    ),
                )

        # ── SWEEP REVERSAL LONG ──────────────────────────────────────────────
        # Large sell sweep hit stops below → now buyers absorbing → expect $100 bounce.
        # Requires: sweep confirmed + velocity flipping + bids strengthening significantly.
        if (
            not self._type_on_cooldown(SignalType.SWEEP_REVERSAL_LONG, now)
            and sweep
            and vel_5s < -V * 1.5       # sweep was strong sell
            and acc_1s > V * 0.5        # now accelerating back up (velocity flipping)
            and imbalance > 0.40        # bids dominating after sweep
            and net_1s > 0             # last second buyers taking control
            and net_3s > -D * 0.3      # sell pressure fading
        ):
            confidence = min(0.72 + abs(imbalance) * 0.25 + min(acc_1s / V, 0.1), 0.95)
            if confidence >= MC:
                return Signal(
                    id=self._next_id(),
                    signal_type=SignalType.SWEEP_REVERSAL_LONG,
                    confidence=confidence,
                    continuation_prob=0.65,
                    velocity_score=min(abs(vel_5s) / (V * 3), 1.0),
                    delta_score=0.7,
                    imbalance_score=imbalance,
                    aggression_score=aggression,
                    price=price,
                    trigger_reason=(
                        f"Sell sweep reversal: imb={imbalance:.2f} "
                        f"acc={acc_1s:,.0f} net1={net_1s:,.0f}"
                    ),
                )

        # ── SWEEP REVERSAL SHORT ─────────────────────────────────────────────
        if (
            not self._type_on_cooldown(SignalType.SWEEP_REVERSAL_SHORT, now)
            and sweep
            and vel_5s > V * 1.5
            and acc_1s < -V * 0.5
            and imbalance < -0.40
            and net_1s < 0
            and net_3s < D * 0.3
        ):
            confidence = min(0.72 + abs(imbalance) * 0.25 + min(abs(acc_1s) / V, 0.1), 0.95)
            if confidence >= MC:
                return Signal(
                    id=self._next_id(),
                    signal_type=SignalType.SWEEP_REVERSAL_SHORT,
                    confidence=confidence,
                    continuation_prob=0.65,
                    velocity_score=min(abs(vel_5s) / (V * 3), 1.0),
                    delta_score=0.7,
                    imbalance_score=abs(imbalance),
                    aggression_score=aggression,
                    price=price,
                    trigger_reason=(
                        f"Buy sweep reversal: imb={imbalance:.2f} "
                        f"acc={acc_1s:,.0f} net1={net_1s:,.0f}"
                    ),
                )

        # ── MOMENTUM EXHAUSTION ──────────────────────────────────────────────
        # Vel 10s was very high, vel 1s now collapsed → move ran out of fuel.
        # Expect mean reversion of $100+.
        # Only valid if peak was recent (<15s) and significant (≥3x min_vel).
        peak_age  = now - self._vel_peak_time
        peak_sig  = self._vel_peak >= V * 3.0   # peak must be strong
        peak_fresh = peak_age < 15.0
        vel_abs_now = abs(vel_5s)
        peak_collapsed = self._vel_peak > 0 and (vel_abs_now / self._vel_peak) < 0.25  # dropped 75%

        if (
            not self._type_on_cooldown(SignalType.MOMENTUM_EXHAUSTION, now)
            and peak_sig
            and peak_fresh
            and peak_collapsed
            and total_5s > D * 0.8   # still some flow — not just quiet market
        ):
            # Reversal direction is opposite to the exhausted move
            reversal_long = self._vel_peak_side == "SELL"

            # Need some sign of reversal in order flow
            if reversal_long and net_1s > 0 and imbalance > 0.20:
                confidence = min(0.70 + (self._vel_peak / (V * 6)) * 0.15, 0.90)
                if confidence >= MC:
                    return Signal(
                        id=self._next_id(),
                        signal_type=SignalType.MOMENTUM_EXHAUSTION,
                        confidence=confidence,
                        continuation_prob=0.60,
                        velocity_score=min(self._vel_peak / (V * 4), 1.0),
                        delta_score=0.65,
                        imbalance_score=imbalance,
                        aggression_score=aggression,
                        price=price,
                        trigger_reason=(
                            f"SELL exhaustion → LONG: peak={self._vel_peak:,.0f} "
                            f"now={vel_abs_now:,.0f} age={peak_age:.0f}s imb={imbalance:.2f}"
                        ),
                    )

            elif not reversal_long and net_1s < 0 and imbalance < -0.20:
                confidence = min(0.70 + (self._vel_peak / (V * 6)) * 0.15, 0.90)
                if confidence >= MC:
                    return Signal(
                        id=self._next_id(),
                        signal_type=SignalType.MOMENTUM_EXHAUSTION,
                        confidence=confidence,
                        continuation_prob=0.60,
                        velocity_score=min(self._vel_peak / (V * 4), 1.0),
                        delta_score=0.65,
                        imbalance_score=abs(imbalance),
                        aggression_score=aggression,
                        price=price,
                        trigger_reason=(
                            f"BUY exhaustion → SHORT: peak={self._vel_peak:,.0f} "
                            f"now={vel_abs_now:,.0f} age={peak_age:.0f}s imb={imbalance:.2f}"
                        ),
                    )

        # ── ABSORPTION REVERSAL ──────────────────────────────────────────────
        # One side hits large orders but price doesn't move → absorbed → reversal.
        # Requires confirmed absorption + directional flow confirmation.
        if (
            not self._type_on_cooldown(SignalType.ABSORPTION_REVERSAL, now)
            and absorption
            and total_5s > D * 1.5      # significant total flow being absorbed
        ):
            # Sellers hitting but price won't drop → buyers absorbing → go long
            if (
                aggression < 0.45       # sellers dominant in flow
                and net_5s < -D * 0.5   # negative net delta
                and net_1s > 0          # but last second buyers winning
                and imbalance > 0.25    # bids strengthening after absorption
                and acc_1s > 0          # upward acceleration beginning
            ):
                confidence = min(0.70 + abs(imbalance) * 0.20 + min(total_5s / (D * 4), 0.08), 0.92)
                if confidence >= MC:
                    return Signal(
                        id=self._next_id(),
                        signal_type=SignalType.ABSORPTION_REVERSAL,
                        confidence=confidence,
                        continuation_prob=0.65,
                        velocity_score=min(total_5s / (D * 3), 1.0),
                        delta_score=min(abs(net_5s) / D, 1.0),
                        imbalance_score=imbalance,
                        aggression_score=aggression,
                        price=price,
                        trigger_reason=(
                            f"Sell absorbed → LONG: total={total_5s:,.0f} "
                            f"imb={imbalance:.2f} net1={net_1s:,.0f}"
                        ),
                    )

            # Buyers hitting but price won't rise → sellers absorbing → go short
            elif (
                aggression > 0.55
                and net_5s > D * 0.5
                and net_1s < 0
                and imbalance < -0.25
                and acc_1s < 0
            ):
                confidence = min(0.70 + abs(imbalance) * 0.20 + min(total_5s / (D * 4), 0.08), 0.92)
                if confidence >= MC:
                    return Signal(
                        id=self._next_id(),
                        signal_type=SignalType.ABSORPTION_REVERSAL,
                        confidence=confidence,
                        continuation_prob=0.65,
                        velocity_score=min(total_5s / (D * 3), 1.0),
                        delta_score=min(abs(net_5s) / D, 1.0),
                        imbalance_score=abs(imbalance),
                        aggression_score=aggression,
                        price=price,
                        trigger_reason=(
                            f"Buy absorbed → SHORT: total={total_5s:,.0f} "
                            f"imb={imbalance:.2f} net1={net_1s:,.0f}"
                        ),
                    )

        return None

    def _next_id(self) -> int:
        self._signal_id_counter += 1
        return self._signal_id_counter

    async def _emit(self, signal: Signal):
        payload = {
            "type": "signal",
            "id": signal.id,
            "signal_type": signal.signal_type,
            "confidence": signal.confidence,
            "continuation_prob": signal.continuation_prob,
            "velocity_score": signal.velocity_score,
            "delta_score": signal.delta_score,
            "imbalance_score": signal.imbalance_score,
            "aggression_score": signal.aggression_score,
            "price": signal.price,
            "trigger_reason": signal.trigger_reason,
            "timestamp": signal.timestamp,
        }
        log.info("Signal", type=signal.signal_type, conf=f"{signal.confidence:.2f}",
                 price=signal.price)
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    cb(payload)
            except Exception as e:
                log.warning("Signal callback error", error=str(e))

    def get_recent_signals(self, limit: int = 50) -> list[dict]:
        signals = self._recent_signals[-limit:]
        return [
            {
                "id": s.id,
                "signal_type": s.signal_type,
                "confidence": s.confidence,
                "continuation_prob": s.continuation_prob,
                "velocity_score": s.velocity_score,
                "delta_score": s.delta_score,
                "imbalance_score": s.imbalance_score,
                "aggression_score": s.aggression_score,
                "price": s.price,
                "trigger_reason": s.trigger_reason,
                "timestamp": s.timestamp,
            }
            for s in reversed(signals)
        ]


signal_engine = SignalEngineService()

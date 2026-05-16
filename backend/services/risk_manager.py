"""
Risk management hub — volatility regime, signal quality, breakout phase,
execution health, loss cooldown, session filter, regime memory.

All market state flows through update() every tick.
Signal evaluation flows through evaluate_signal() before execution.
"""

import time
from datetime import datetime, timezone
from enum import Enum
from dataclasses import dataclass

import structlog

from config import settings

log = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------

class VolatilityRegime(str, Enum):
    LOW_VOL_CHOP = "LOW_VOL_CHOP"
    NORMAL_TREND = "NORMAL_TREND"
    HIGH_VOL_EXP = "HIGH_VOL_EXP"
    LIQUIDATION  = "LIQUIDATION"
    EXHAUSTION   = "EXHAUSTION"


class BreakoutPhase(str, Enum):
    EARLY    = "EARLY"
    MID      = "MID"
    LATE     = "LATE"
    EXHAUSTED = "EXHAUSTED"


class ExecHealth(str, Enum):
    EXCELLENT = "EXCELLENT"
    GOOD      = "GOOD"
    DEGRADED  = "DEGRADED"
    UNSAFE    = "UNSAFE"


class Session(str, Enum):
    LONDON_NY = "LONDON_NY"   # 13-17 UTC — best
    NY        = "NY"           # 17-22 UTC — good
    LONDON    = "LONDON"       # 07-13 UTC — good
    ASIAN     = "ASIAN"        # 00-07 UTC — lower quality
    DEAD      = "DEAD"         # 22-00 UTC — blocked


# ---------------------------------------------------------------------------
# Dataclass
# ---------------------------------------------------------------------------

@dataclass
class AdaptiveParams:
    sl: float
    tp: float
    rr: float
    regime: str
    quality_min: int


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REGIME_PARAMS: dict[VolatilityRegime, AdaptiveParams] = {
    VolatilityRegime.LOW_VOL_CHOP: AdaptiveParams(sl=30,  tp=90,  rr=3.0, regime=VolatilityRegime.LOW_VOL_CHOP.value,  quality_min=82),
    VolatilityRegime.NORMAL_TREND: AdaptiveParams(sl=40,  tp=120, rr=3.0, regime=VolatilityRegime.NORMAL_TREND.value, quality_min=70),
    VolatilityRegime.HIGH_VOL_EXP: AdaptiveParams(sl=65,  tp=195, rr=3.0, regime=VolatilityRegime.HIGH_VOL_EXP.value, quality_min=64),
    VolatilityRegime.LIQUIDATION:  AdaptiveParams(sl=80,  tp=240, rr=3.0, regime=VolatilityRegime.LIQUIDATION.value,  quality_min=58),
    VolatilityRegime.EXHAUSTION:   AdaptiveParams(sl=35,  tp=105, rr=3.0, regime=VolatilityRegime.EXHAUSTION.value,   quality_min=76),
}

TRADEABLE_REGIMES: set[VolatilityRegime] = {
    VolatilityRegime.NORMAL_TREND,
    VolatilityRegime.HIGH_VOL_EXP,
    VolatilityRegime.LIQUIDATION,
}

EXEC_HEALTH_RANK: dict[ExecHealth, int] = {
    ExecHealth.EXCELLENT: 4,
    ExecHealth.GOOD:      3,
    ExecHealth.DEGRADED:  2,
    ExecHealth.UNSAFE:    1,
}

# Velocity / delta thresholds for scoring
_V = 200_000   # base velocity threshold
_D = 600_000   # base delta threshold

# How many spread samples to collect before computing baseline
_SPREAD_BASELINE_SAMPLES = 80

# Peak staleness — reset velocity peak after this many seconds of no update
_VEL_PEAK_TTL = 35.0


# ---------------------------------------------------------------------------
# RiskManager
# ---------------------------------------------------------------------------

class RiskManager:
    def __init__(self) -> None:
        self._last_market: dict = {}

        # Regime
        self._current_regime: VolatilityRegime = VolatilityRegime.NORMAL_TREND
        self._vel_peak: float = 0.0
        self._vel_peak_side: str = ""
        self._vel_peak_time: float = 0.0
        self._move_start_time: float = time.time()
        self._move_side: str = ""   # "BUY" | "SELL" | ""

        # Execution health
        self._spread_samples: list[float] = []
        self._spread_baseline: float = 0.0
        self._exec_health: ExecHealth = ExecHealth.GOOD   # conservative until baseline established
        self._exec_health_score: float = 1.0   # spread ratio

        # Session
        self._current_session: Session = self._classify_session()

        # Cooldown
        self._consecutive_losses: int = 0
        self._cooldown_until: float = 0.0
        self._cooldown_reason: str = ""

        # Regime memory (last 100 trades)
        self._regime_memory: list[dict] = []

        # Same-direction cooldown — prevents rapid same-side signal spam
        self._last_allowed_direction: str = ""      # "LONG" | "SHORT"
        self._last_allowed_direction_time: float = 0.0
        self._last_exec_direction: str = ""         # updated on actual MT5 open
        self._last_exec_direction_time: float = 0.0

    # ------------------------------------------------------------------
    # Public: tick update
    # ------------------------------------------------------------------

    def update(self, market: dict) -> None:
        """Called on every market tick. Updates all internal state."""
        self._last_market = market
        now = time.time()

        velocity = market.get("velocity", {})
        net_delta = market.get("net_delta", {})

        vel5_signed: float = velocity.get(5, 0.0)
        vel5: float = abs(vel5_signed)
        vel10: float = abs(velocity.get(10, 0.0))
        net5: float = abs(net_delta.get(5, 0.0))
        sweep: bool = bool(market.get("sweep_detected", False))

        # --- Classify regime ---
        self._current_regime = self._classify_regime(vel5, vel5_signed, vel10, net5, sweep, now)

        # --- Velocity peak tracking (for exhaustion detection) ---
        side = "BUY" if vel5_signed >= 0 else "SELL"
        peak_stale = (now - self._vel_peak_time) > _VEL_PEAK_TTL

        if side != self._vel_peak_side or peak_stale:
            # Side flipped or peak expired — reset
            self._vel_peak = 0.0
            self._vel_peak_side = side
            self._vel_peak_time = now

        if vel5 > self._vel_peak:
            self._vel_peak = vel5
            self._vel_peak_time = now

        # --- Move tracking (for breakout phase) ---
        if self._move_side != "" and side != self._move_side and vel5 > 80_000:
            # Direction changed — start a new move
            self._move_start_time = now
        elif self._move_side == "":
            self._move_start_time = now

        self._move_side = side

        # --- Execution health ---
        spread: float = float(market.get("spread", 0.0))
        if spread > 0:
            self._update_exec_health(spread)

        # --- Session ---
        self._current_session = self._classify_session()

        log.debug(
            "risk_manager.update",
            regime=self._current_regime.value,
            session=self._current_session.value,
            exec_health=self._exec_health.value,
            vel5=round(vel5, 0),
        )

    # ------------------------------------------------------------------
    # Public: signal evaluation
    # ------------------------------------------------------------------

    def evaluate_signal(self, signal: dict, market: dict) -> dict:
        """
        Evaluate whether a signal should be executed.

        Returns:
            {
                allowed: bool,
                quality_score: int,
                breakout_phase: str,
                regime: str,
                skip_reason: str,
            }
        """
        regime = self._current_regime
        result_base = {
            "regime": regime.value,
            "quality_score": 0,
            "breakout_phase": BreakoutPhase.EARLY.value,
            "skip_reason": "",
            "allowed": False,
        }

        # 1. Regime gate
        if regime not in TRADEABLE_REGIMES:
            return {**result_base, "skip_reason": f"Regime={regime.value} not tradeable"}

        # 2. Execution health gate
        required_health = ExecHealth(settings.exec_health_min)
        required_rank = EXEC_HEALTH_RANK[required_health]
        actual_rank = EXEC_HEALTH_RANK[self._exec_health]
        if actual_rank < required_rank:
            return {
                **result_base,
                "skip_reason": (
                    f"ExecHealth={self._exec_health.value} below required "
                    f"{settings.exec_health_min} (spread_ratio={self._exec_health_score:.2f})"
                ),
            }

        # 3. Cooldown gate
        cooldown = self.get_cooldown_state()
        if cooldown["active"]:
            return {
                **result_base,
                "skip_reason": (
                    f"Cooldown active: {cooldown['reason']} "
                    f"({cooldown['remaining_seconds']}s remaining)"
                ),
            }

        # 4. Session gate
        if self._current_session.value in settings.blocked_sessions:
            return {
                **result_base,
                "skip_reason": f"Session={self._current_session.value} is blocked",
            }

        # 5. Same-direction cooldown — suppresses duplicate signals after recent allow
        sig_type_for_dir = signal.get("signal_type", "")
        direction = (
            "LONG" if ("LONG" in sig_type_for_dir or sig_type_for_dir == "ABSORPTION_REVERSAL")
            else "SHORT"
        )
        cooldown_dir = getattr(settings, "cooldown_between_same_direction_signals", 30.0)
        if direction == self._last_allowed_direction and cooldown_dir > 0:
            elapsed = time.time() - self._last_allowed_direction_time
            if elapsed < cooldown_dir:
                remaining = cooldown_dir - elapsed
                return {
                    **result_base,
                    "skip_reason": (
                        f"Same-direction cooldown ({direction}): "
                        f"{remaining:.0f}s remaining"
                    ),
                }

        # 6. Quality score
        quality_score = self._score_signal(signal, market, regime)
        quality_min = REGIME_PARAMS[regime].quality_min

        # 6. Breakout phase
        breakout_phase = self._classify_breakout(market)

        if breakout_phase == BreakoutPhase.LATE:
            quality_score = max(0, quality_score - 12)

        if quality_score < quality_min:
            return {
                **result_base,
                "quality_score": quality_score,
                "breakout_phase": breakout_phase.value,
                "skip_reason": (
                    f"Quality={quality_score} below min={quality_min} "
                    f"for regime={regime.value}"
                ),
            }

        if breakout_phase == BreakoutPhase.EXHAUSTED:
            return {
                **result_base,
                "quality_score": quality_score,
                "breakout_phase": breakout_phase.value,
                "skip_reason": "Breakout phase=EXHAUSTED",
            }

        # 7. Allowed — record direction to enforce same-direction cooldown
        self._last_allowed_direction = direction
        self._last_allowed_direction_time = time.time()
        return {
            "allowed": True,
            "quality_score": quality_score,
            "breakout_phase": breakout_phase.value,
            "regime": regime.value,
            "skip_reason": "",
        }

    # ------------------------------------------------------------------
    # Public: results & cooldown
    # ------------------------------------------------------------------

    def record_result(
        self,
        profit: float,
        signal_type: str = "",
        session: str = "",
        regime: str = "",
    ) -> None:
        """Record a trade result and manage consecutive-loss cooldown."""
        now = time.time()

        if profit < 0:
            self._consecutive_losses += 1
            losses = self._consecutive_losses

            if losses >= settings.cooldown_losses_hard:
                self._cooldown_until = now + settings.cooldown_hard_seconds
                self._cooldown_reason = (
                    f"Hard cooldown: {losses} consecutive losses "
                    f"({settings.cooldown_hard_seconds}s pause)"
                )
                log.warning(
                    "risk_manager.cooldown.hard",
                    consecutive_losses=losses,
                    cooldown_seconds=settings.cooldown_hard_seconds,
                )
            elif losses >= settings.cooldown_losses_medium:
                self._cooldown_until = now + settings.cooldown_medium_seconds
                self._cooldown_reason = (
                    f"Medium cooldown: {losses} consecutive losses "
                    f"({settings.cooldown_medium_seconds}s pause)"
                )
                log.info(
                    "risk_manager.cooldown.medium",
                    consecutive_losses=losses,
                    cooldown_seconds=settings.cooldown_medium_seconds,
                )
        else:
            if self._consecutive_losses > 0:
                log.info(
                    "risk_manager.loss_streak_reset",
                    previous_streak=self._consecutive_losses,
                )
            self._consecutive_losses = 0

        # Append to regime memory (cap at 100)
        entry = {
            "profit": profit,
            "signal_type": signal_type,
            "session": session or self._current_session.value,
            "regime": regime or self._current_regime.value,
            "ts": now,
        }
        self._regime_memory.append(entry)
        if len(self._regime_memory) > 100:
            self._regime_memory = self._regime_memory[-100:]

    def record_execution(self, direction: str) -> None:
        """Called immediately after a successful MT5 open. Resets same-direction cooldown."""
        self._last_exec_direction = direction
        self._last_exec_direction_time = time.time()
        # Execution resets the allowed cooldown too (we just traded)
        self._last_allowed_direction = direction
        self._last_allowed_direction_time = time.time()

    def get_cooldown_state(self) -> dict:
        now = time.time()
        remaining = max(0.0, self._cooldown_until - now)
        return {
            "active": remaining > 0,
            "remaining_seconds": round(remaining, 1),
            "reason": self._cooldown_reason if remaining > 0 else "",
            "consecutive_losses": self._consecutive_losses,
        }

    # ------------------------------------------------------------------
    # Public: stats & status
    # ------------------------------------------------------------------

    def get_regime_stats(self) -> dict:
        """Group regime_memory by regime and session; return win_rate, count, net_pnl."""
        stats: dict[str, dict] = {}

        for entry in self._regime_memory:
            key = f"{entry['regime']}|{entry['session']}"
            if key not in stats:
                stats[key] = {"regime": entry["regime"], "session": entry["session"],
                              "wins": 0, "count": 0, "net_pnl": 0.0}
            stats[key]["count"] += 1
            stats[key]["net_pnl"] = round(stats[key]["net_pnl"] + entry["profit"], 4)
            if entry["profit"] >= 0:
                stats[key]["wins"] += 1

        result = {}
        for key, s in stats.items():
            result[key] = {
                "regime": s["regime"],
                "session": s["session"],
                "count": s["count"],
                "win_rate": round(s["wins"] / s["count"], 3) if s["count"] else 0.0,
                "net_pnl": s["net_pnl"],
            }
        return result

    def get_adaptive_params(self) -> AdaptiveParams:
        """Return SL/TP/RR params for the current regime."""
        return REGIME_PARAMS[self._current_regime]

    def status_dict(self) -> dict:
        """Return all state the frontend needs in one call."""
        params = self.get_adaptive_params()
        return {
            "regime": self._current_regime.value,
            "session": self._current_session.value,
            "exec_health": self._exec_health.value,
            "exec_spread_ratio": round(self._exec_health_score, 2),
            "cooldown": self.get_cooldown_state(),
            "adaptive": {
                "sl": params.sl,
                "tp": params.tp,
                "rr": params.rr,
            },
            "consecutive_losses": self._consecutive_losses,
            "tradeable": self._current_regime in TRADEABLE_REGIMES,
        }

    # ------------------------------------------------------------------
    # Properties
    # ------------------------------------------------------------------

    @property
    def current_regime(self) -> str:
        return self._current_regime.value

    @property
    def current_session(self) -> str:
        return self._current_session.value

    @property
    def exec_health(self) -> str:
        return self._exec_health.value

    @property
    def adaptive_params(self) -> AdaptiveParams:
        return REGIME_PARAMS[self._current_regime]

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _classify_regime(
        self,
        vel5: float,
        vel5_signed: float,
        vel10: float,
        net5: float,
        sweep: bool,
        now: float,
    ) -> VolatilityRegime:
        # LIQUIDATION: extreme velocity + sweep + large net delta
        if vel5 > 700_000 and sweep and net5 > 1_200_000:
            return VolatilityRegime.LIQUIDATION

        # HIGH_VOL_EXP: sustained high velocity
        if vel5 > 300_000 and vel10 > 180_000:
            return VolatilityRegime.HIGH_VOL_EXP

        # EXHAUSTION: velocity collapsed after strong peak (within 30s)
        peak_recent = (now - self._vel_peak_time) < 30
        if (
            self._vel_peak > 450_000
            and vel5 < self._vel_peak * 0.20
            and peak_recent
        ):
            return VolatilityRegime.EXHAUSTION

        # NORMAL_TREND: moderate but real momentum
        if vel5 > 100_000 and vel10 > 60_000:
            return VolatilityRegime.NORMAL_TREND

        # Default
        return VolatilityRegime.LOW_VOL_CHOP

    def _classify_breakout(self, market: dict) -> BreakoutPhase:
        vel5 = abs(market.get("velocity", {}).get(5, 0.0))

        # Primary: velocity-decay ratio — how much momentum remains vs peak
        if self._vel_peak > _V * 0.5:
            decay_ratio = vel5 / self._vel_peak if self._vel_peak > 0 else 0.0
            if decay_ratio > 0.75:
                return BreakoutPhase.EARLY
            if decay_ratio > 0.50:
                return BreakoutPhase.MID
            if decay_ratio > 0.25:
                return BreakoutPhase.LATE
            return BreakoutPhase.EXHAUSTED

        # Fallback: time-based for low-velocity / quiet markets
        move_age = time.time() - self._move_start_time
        if move_age < 10:
            return BreakoutPhase.EARLY
        if move_age < 25:
            return BreakoutPhase.MID
        if move_age < 50:
            return BreakoutPhase.LATE
        return BreakoutPhase.EXHAUSTED

    def _classify_session(self) -> Session:
        h = datetime.now(timezone.utc).hour
        if 13 <= h < 17:
            return Session.LONDON_NY
        if 17 <= h < 22:
            return Session.NY
        if 7 <= h < 13:
            return Session.LONDON
        if 0 <= h < 7:
            return Session.ASIAN
        return Session.DEAD

    def _update_exec_health(self, spread: float) -> None:
        """Collect spread samples, compute baseline on first 80, then classify."""
        if len(self._spread_samples) < _SPREAD_BASELINE_SAMPLES:
            self._spread_samples.append(spread)
            if len(self._spread_samples) == _SPREAD_BASELINE_SAMPLES:
                # Compute baseline as the 20th percentile to avoid outlier inflation
                sorted_samples = sorted(self._spread_samples)
                p20_idx = max(0, int(len(sorted_samples) * 0.20) - 1)
                self._spread_baseline = sorted_samples[p20_idx]
                log.info(
                    "risk_manager.spread_baseline_set",
                    baseline=round(self._spread_baseline, 4),
                )
            return  # Still collecting — keep EXCELLENT default

        if self._spread_baseline <= 0:
            return

        ratio = spread / self._spread_baseline
        self._exec_health_score = ratio

        if ratio < 1.8:
            self._exec_health = ExecHealth.EXCELLENT
        elif ratio < 3.5:
            self._exec_health = ExecHealth.GOOD
        elif ratio < 6.0:
            self._exec_health = ExecHealth.DEGRADED
        else:
            self._exec_health = ExecHealth.UNSAFE

    def _score_signal(
        self,
        signal: dict,
        market: dict,
        regime: VolatilityRegime,
    ) -> int:
        """
        Composite quality score 0-100.

        Components:
          vel_score    0-22   velocity strength
          delta_score  0-20   delta persistence / 10s conviction
          imb_score    0-14   imbalance conviction
          cont_score   0-14   continuation probability
          entry_clean  0-14   entry cleanliness (absorption penalty)
          regime_bonus 0-10   regime quality bonus
          conf_bonus   0-6    signal confidence bonus
        """
        velocity = market.get("velocity", {})
        net_delta = market.get("net_delta", {})

        vel5: float  = abs(velocity.get(5, 0.0))
        vel10: float = abs(velocity.get(10, 0.0))  # noqa: F841 — captured for future use
        net10: float = abs(net_delta.get(10, 0.0))
        imbalance: float = abs(market.get("imbalance", 0.0))
        cont_prob: float = float(market.get("continuation_prob", 0.0))
        absorption: bool = bool(market.get("absorption_detected", False))
        conf: float = float(signal.get("confidence", 0.0))
        sig_type: str = signal.get("signal_type", "")

        # 1. Velocity strength (0-22)
        vel_score = min(vel5 / (_V * 4), 1.0) * 22

        # 2. Delta persistence / 10s conviction (0-20)
        delta_score = min(net10 / (_D * 2), 1.0) * 20

        # 3. Imbalance conviction (0-14)
        imb_score = min(imbalance / 0.55, 1.0) * 14

        # 4. Continuation quality (0-14)
        cont_score = max(0.0, (cont_prob - 0.45) / 0.45) * 14

        # 5. Entry cleanliness (0-14): absorption against the signal direction is bad
        sig_is_long: bool = "LONG" in sig_type or sig_type == "ABSORPTION_REVERSAL"
        imb_signed: float = float(market.get("imbalance", 0.0))
        absorb_penalty = 0
        if absorption:
            if sig_is_long and imb_signed < -0.20:
                absorb_penalty = 10
            if not sig_is_long and imb_signed > 0.20:
                absorb_penalty = 10
        entry_clean = max(0.0, 14 - absorb_penalty)

        # 6. Regime bonus (0-10)
        regime_bonus_map: dict[VolatilityRegime, int] = {
            VolatilityRegime.LIQUIDATION:  10,
            VolatilityRegime.HIGH_VOL_EXP: 8,
            VolatilityRegime.NORMAL_TREND:  6,
            VolatilityRegime.EXHAUSTION:    4,
            VolatilityRegime.LOW_VOL_CHOP:  0,
        }
        regime_bonus = regime_bonus_map.get(regime, 0)

        # 7. Signal confidence bonus (0-6)
        conf_bonus = min((conf - 0.70) / 0.20, 1.0) * 6 if conf > 0.70 else 0.0

        total = (
            vel_score
            + delta_score
            + imb_score
            + cont_score
            + entry_clean
            + regime_bonus
            + conf_bonus
        )
        return int(min(100, max(0, total)))


# ---------------------------------------------------------------------------
# Singleton
# ---------------------------------------------------------------------------

risk_manager = RiskManager()

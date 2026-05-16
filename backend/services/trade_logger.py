"""
Persistent trade and signal logger.

Writes every signal (fired or gated) and every trade (open + close) to SQLite.
Provides read endpoints for the API layer.
"""
import time
from datetime import datetime, timezone
from typing import Optional

import structlog
from sqlalchemy import text as sql_text

from database.db import AsyncSessionLocal
from database.models import Signal as SignalModel, Trade as TradeModel

log = structlog.get_logger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class TradeLogger:

    # ------------------------------------------------------------------
    # Signals
    # ------------------------------------------------------------------

    async def log_signal(
        self,
        signal: dict,
        evaluation: dict,
        ai_bias: str,
        executed: bool,
    ) -> None:
        """
        Log every signal that passed the signal engine — regardless of whether
        it was gated by risk_manager or AI bias.

        Args:
            signal:     raw signal dict from signal_engine (includes quality_score etc.)
            evaluation: risk_manager.evaluate_signal() result
            ai_bias:    current AI bias at time of signal
            executed:   True if an MT5 order was actually sent
        """
        allowed = evaluation.get("allowed", False)
        skip_reason = evaluation.get("skip_reason", "")

        # If risk_manager allowed it but AI bias blocked it, record that
        if allowed and not executed and not skip_reason:
            skip_reason = f"AI bias={ai_bias} blocked direction"

        row = SignalModel(
            signal_type=signal.get("signal_type", ""),
            confidence=signal.get("confidence", 0.0),
            continuation_prob=signal.get("continuation_prob", 0.0),
            velocity_score=signal.get("velocity_score", 0.0),
            delta_score=signal.get("delta_score", 0.0),
            imbalance_score=signal.get("imbalance_score", 0.0),
            aggression_score=signal.get("aggression_score", 0.0),
            price=signal.get("price", 0.0),
            trigger_reason=(signal.get("trigger_reason") or "")[:500],
            quality_score=evaluation.get("quality_score"),
            breakout_phase=evaluation.get("breakout_phase"),
            regime=evaluation.get("regime"),
            session=self._current_session(),
            ai_bias=ai_bias,
            executed=executed,
            skipped=not allowed,
            skip_reason=skip_reason[:200] if skip_reason else None,
            created_at=_utcnow(),
        )
        try:
            async with AsyncSessionLocal() as session:
                session.add(row)
                await session.commit()
                # Keep only latest 500 signals — delete older ones
                await session.execute(
                    sql_text("DELETE FROM signals WHERE id NOT IN "
                             "(SELECT id FROM signals ORDER BY id DESC LIMIT 500)")
                )
                await session.commit()
                log.debug("signal logged", type=row.signal_type, executed=executed,
                          quality=row.quality_score, skipped=row.skipped)
        except Exception as e:
            log.error("signal log failed", error=str(e))

    async def get_recent_signals(self, limit: int = 50) -> list[dict]:
        from sqlalchemy import select
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(SignalModel)
                    .order_by(SignalModel.id.desc())
                    .limit(limit)
                )
                rows = result.scalars().all()
                return [self._signal_to_dict(r) for r in rows]
        except Exception as e:
            log.error("get_recent_signals failed", error=str(e))
            return []

    # ------------------------------------------------------------------
    # Trades
    # ------------------------------------------------------------------

    async def log_trade_open(
        self,
        mt5_ticket: int,
        side: str,
        symbol: str,
        entry_price: float,
        lot_size: float,
        commission: float,
        signal: Optional[dict] = None,
        evaluation: Optional[dict] = None,
        adaptive_sl: Optional[float] = None,
        adaptive_tp: Optional[float] = None,
    ) -> None:
        row = TradeModel(
            mt5_ticket=mt5_ticket,
            mt5_symbol=symbol,
            side=side,
            entry_price=entry_price,
            lot_size=lot_size,
            commission=commission,
            swap=0.0,
            pnl=None,
            status="OPEN",
            signal_id=signal.get("id") if signal else None,
            signal_confidence=signal.get("confidence") if signal else None,
            signal_quality_score=signal.get("quality_score") if signal else None,
            signal_breakout_phase=signal.get("breakout_phase") if signal else None,
            regime=evaluation.get("regime") if evaluation else None,
            session=self._current_session(),
            adaptive_sl=adaptive_sl,
            adaptive_tp=adaptive_tp,
            opened_at=_utcnow(),
        )
        try:
            async with AsyncSessionLocal() as session:
                session.add(row)
                await session.commit()
                log.info("trade open logged", ticket=mt5_ticket, side=side, price=entry_price)
        except Exception as e:
            log.error("trade open log failed", error=str(e))

    async def log_trade_close(
        self,
        mt5_ticket: int,
        exit_price: float,
        pnl: float,
        swap: float,
        exit_reason: str,
        duration_seconds: float,
    ) -> None:
        from sqlalchemy import select, update
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TradeModel)
                    .where(TradeModel.mt5_ticket == mt5_ticket)
                    .where(TradeModel.status == "OPEN")
                )
                row = result.scalar_one_or_none()
                if row is None:
                    log.warning("trade close — ticket not found in DB", ticket=mt5_ticket)
                    return
                row.exit_price = exit_price
                row.pnl = pnl
                row.swap = swap
                row.status = "CLOSED"
                row.exit_reason = exit_reason
                row.duration_seconds = duration_seconds
                row.closed_at = _utcnow()
                await session.commit()
                log.info("trade close logged", ticket=mt5_ticket, pnl=pnl, reason=exit_reason)
        except Exception as e:
            log.error("trade close log failed", error=str(e))

    async def get_recent_trades(self, limit: int = 50) -> list[dict]:
        from sqlalchemy import select
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TradeModel)
                    .order_by(TradeModel.id.desc())
                    .limit(limit)
                )
                rows = result.scalars().all()
                return [self._trade_to_dict(r) for r in rows]
        except Exception as e:
            log.error("get_recent_trades failed", error=str(e))
            return []

    async def get_open_trade_by_ticket(self, mt5_ticket: int) -> Optional[dict]:
        from sqlalchemy import select
        try:
            async with AsyncSessionLocal() as session:
                result = await session.execute(
                    select(TradeModel)
                    .where(TradeModel.mt5_ticket == mt5_ticket)
                    .where(TradeModel.status == "OPEN")
                )
                row = result.scalar_one_or_none()
                return self._trade_to_dict(row) if row else None
        except Exception as e:
            log.error("get_open_trade failed", error=str(e))
            return None

    # ------------------------------------------------------------------
    # Serializers
    # ------------------------------------------------------------------

    def _signal_to_dict(self, r: SignalModel) -> dict:
        return {
            "id": r.id,
            "signal_type": r.signal_type,
            "confidence": r.confidence,
            "continuation_prob": r.continuation_prob,
            "velocity_score": r.velocity_score,
            "delta_score": r.delta_score,
            "imbalance_score": r.imbalance_score,
            "aggression_score": r.aggression_score,
            "price": r.price,
            "trigger_reason": r.trigger_reason,
            "quality_score": r.quality_score,
            "breakout_phase": r.breakout_phase,
            "regime": r.regime,
            "session": r.session,
            "ai_bias": r.ai_bias,
            "executed": r.executed,
            "skipped": r.skipped,
            "skip_reason": r.skip_reason,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }

    def _trade_to_dict(self, r: TradeModel) -> dict:
        return {
            "id": r.id,
            "mt5_ticket": r.mt5_ticket,
            "mt5_symbol": r.mt5_symbol,
            "side": r.side,
            "entry_price": r.entry_price,
            "exit_price": r.exit_price,
            "lot_size": r.lot_size,
            "commission": r.commission,
            "swap": r.swap,
            "pnl": r.pnl,
            "status": r.status,
            "exit_reason": r.exit_reason,
            "signal_id": r.signal_id,
            "signal_confidence": r.signal_confidence,
            "signal_quality_score": r.signal_quality_score,
            "signal_breakout_phase": r.signal_breakout_phase,
            "regime": r.regime,
            "session": r.session,
            "adaptive_sl": r.adaptive_sl,
            "adaptive_tp": r.adaptive_tp,
            "duration_seconds": r.duration_seconds,
            "opened_at": r.opened_at.isoformat() if r.opened_at else None,
            "closed_at": r.closed_at.isoformat() if r.closed_at else None,
        }

    def _current_session(self) -> str:
        from datetime import datetime, timezone
        h = datetime.now(timezone.utc).hour
        if 13 <= h < 17: return "LONDON_NY"
        if 17 <= h < 22: return "NY"
        if  7 <= h < 13: return "LONDON"
        if  0 <= h <  7: return "ASIAN"
        return "DEAD"


trade_logger = TradeLogger()

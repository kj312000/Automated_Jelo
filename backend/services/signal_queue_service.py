"""
Persistent signal queue for decoupled MT5 execution.

Flow (Railway deployment):
  1. Backend validates signal → enqueue()
  2. Local Windows executor polls get_pending()
  3. Executor runs MT5 trade → ack(id, "EXECUTED", mt5_ticket=...)
  4. Signals expire after signal_queue_expiry_seconds if never claimed

Flow (local deployment, MT5 connected):
  Signal is executed directly AND enqueued — ack() called automatically
  after MT5 confirms the open.

Endpoints (exposed by main.py):
  GET  /api/executor/queue          → get_pending()
  POST /api/executor/queue/{id}/ack → ack()
  GET  /api/executor/queue/recent   → get_recent()
"""
from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import SignalQueue as QueueModel

log = structlog.get_logger(__name__)

_DEFAULT_EXPIRY_SECONDS = 60


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SignalQueueService:

    async def enqueue(
        self,
        signal: dict,
        side: str,
        adaptive_sl: float,
        adaptive_tp: float,
        expiry_seconds: float | None = None,
    ) -> int | None:
        """Persist validated signal to queue. Returns row id or None on failure."""
        from config import settings
        exp = expiry_seconds or getattr(settings, "signal_queue_expiry_seconds", _DEFAULT_EXPIRY_SECONDS)
        now = _utcnow()
        row = QueueModel(
            signal_type=signal.get("signal_type", ""),
            side=side,
            confidence=signal.get("confidence", 0.0),
            price=signal.get("price", 0.0),
            quality_score=signal.get("quality_score"),
            regime=signal.get("regime"),
            adaptive_sl=adaptive_sl,
            adaptive_tp=adaptive_tp,
            payload=signal,
            status="PENDING",
            created_at=now,
            expires_at=now + timedelta(seconds=exp),
        )
        try:
            async with AsyncSessionLocal() as session:
                session.add(row)
                await session.commit()
                log.info("signal_queue.enqueued",
                         id=row.id, type=row.signal_type, side=side, exp=exp)
                return row.id
        except Exception as exc:
            log.error("signal_queue.enqueue_failed", error=str(exc))
            return None

    async def get_pending(self, limit: int = 20) -> list[dict]:
        """Return PENDING, non-expired signals for the local executor to claim."""
        now = _utcnow()
        try:
            async with AsyncSessionLocal() as session:
                rows = (await session.execute(
                    select(QueueModel)
                    .where(QueueModel.status == "PENDING")
                    .where(QueueModel.expires_at > now)
                    .order_by(QueueModel.id.asc())
                    .limit(limit)
                )).scalars().all()
                return [self._to_dict(r) for r in rows]
        except Exception as exc:
            log.error("signal_queue.get_pending_failed", error=str(exc))
            return []

    async def ack(
        self,
        queue_id: int,
        status: str,         # "EXECUTED" | "FAILED"
        error: str = "",
        mt5_ticket: int | None = None,
    ) -> bool:
        if status not in {"EXECUTED", "FAILED"}:
            return False
        try:
            async with AsyncSessionLocal() as session:
                row = (await session.execute(
                    select(QueueModel).where(QueueModel.id == queue_id)
                )).scalar_one_or_none()
                if not row:
                    return False
                row.status = status
                row.executed_at = _utcnow()
                row.error = error or None
                row.mt5_ticket = mt5_ticket
                await session.commit()
                log.info("signal_queue.acked",
                         id=queue_id, status=status, ticket=mt5_ticket)
                return True
        except Exception as exc:
            log.error("signal_queue.ack_failed", error=str(exc))
            return False

    async def expire_old(self) -> int:
        """Mark stale PENDING entries as EXPIRED. Called on executor heartbeat."""
        now = _utcnow()
        try:
            async with AsyncSessionLocal() as session:
                rows = (await session.execute(
                    select(QueueModel)
                    .where(QueueModel.status == "PENDING")
                    .where(QueueModel.expires_at <= now)
                )).scalars().all()
                for row in rows:
                    row.status = "EXPIRED"
                await session.commit()
                if rows:
                    log.info("signal_queue.expired", count=len(rows))
                return len(rows)
        except Exception as exc:
            log.error("signal_queue.expire_failed", error=str(exc))
            return 0

    async def get_recent(self, limit: int = 50) -> list[dict]:
        """Most-recent queue entries for the logs view."""
        try:
            async with AsyncSessionLocal() as session:
                rows = (await session.execute(
                    select(QueueModel).order_by(QueueModel.id.desc()).limit(limit)
                )).scalars().all()
                return [self._to_dict(r) for r in rows]
        except Exception as exc:
            log.error("signal_queue.get_recent_failed", error=str(exc))
            return []

    def _to_dict(self, r: QueueModel) -> dict:
        return {
            "id": r.id,
            "signal_type": r.signal_type,
            "side": r.side,
            "confidence": r.confidence,
            "price": r.price,
            "quality_score": r.quality_score,
            "regime": r.regime,
            "adaptive_sl": r.adaptive_sl,
            "adaptive_tp": r.adaptive_tp,
            "payload": r.payload,
            "status": r.status,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "expires_at": r.expires_at.isoformat() if r.expires_at else None,
            "executed_at": r.executed_at.isoformat() if r.executed_at else None,
            "mt5_ticket": r.mt5_ticket,
            "error": r.error,
        }


signal_queue_service = SignalQueueService()

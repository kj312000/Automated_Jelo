"""
Simulated Exness execution engine.
Models commissions, slippage, latency, MFE/MAE tracking, and exit conditions.
"""
import asyncio
import time
import random
from dataclasses import dataclass, field
from typing import Callable, Optional
import structlog

from config import settings

log = structlog.get_logger(__name__)


@dataclass
class SimulatedTrade:
    id: int
    side: str                       # BUY / SELL
    entry_price: float
    lot_size: float
    commission: float
    slippage: float
    latency_ms: float
    signal_id: Optional[int]
    signal_confidence: Optional[float]
    opened_at: float = field(default_factory=time.time)

    # Tracking
    current_price: float = 0.0
    unrealized_pnl: float = 0.0
    mfe: float = 0.0
    mae: float = 0.0
    status: str = "OPEN"

    # Closed
    exit_price: float = 0.0
    pnl: float = 0.0
    exit_reason: str = ""
    closed_at: float = 0.0
    duration_seconds: float = 0.0


class ExecutionSimulatorService:
    def __init__(self):
        self._trades: dict[int, SimulatedTrade] = {}
        self._trade_id_counter = 0
        self._callbacks: list[Callable] = []
        self._auto_execute = False
        self._running = False
        self._current_price: float = 0.0
        self._lot_size = settings.default_lot_size

    @property
    def is_running(self) -> bool:
        return self._running

    @property
    def auto_execute(self) -> bool:
        return self._auto_execute

    def set_auto_execute(self, enabled: bool):
        self._auto_execute = enabled
        log.info("Auto-execute", enabled=enabled)

    def set_lot_size(self, lot_size: float):
        self._lot_size = lot_size

    def subscribe(self, callback: Callable):
        self._callbacks.append(callback)

    def start(self):
        self._running = True
        log.info("ExecutionSimulator started")

    def stop(self):
        self._running = False

    def update_price(self, price: float):
        self._current_price = price
        self._update_open_trades(price)

    async def on_signal(self, signal: dict):
        if not self._auto_execute or not self._running:
            return

        sig_type = signal.get("signal_type", "")
        confidence = signal.get("confidence", 0.0)

        if confidence < settings.min_confidence:
            return

        # Only one open trade at a time for safety
        open_trades = [t for t in self._trades.values() if t.status == "OPEN"]
        if len(open_trades) > 0:
            return

        if "LONG" in sig_type or sig_type == "ABSORPTION_REVERSAL":
            await self.open_trade("BUY", signal_id=signal.get("id"), confidence=confidence)
        elif "SHORT" in sig_type:
            await self.open_trade("SELL", signal_id=signal.get("id"), confidence=confidence)

    async def open_trade(
        self,
        side: str,
        signal_id: Optional[int] = None,
        confidence: Optional[float] = None,
    ) -> Optional[SimulatedTrade]:
        if not self._running:
            return None
        if self._current_price == 0.0:
            return None

        # Simulate latency
        latency_ms = settings.latency_ms + random.gauss(0, 5)
        await asyncio.sleep(latency_ms / 1000.0)

        # Simulate slippage
        slippage_usd = self._current_price * settings.slippage_bps / 10000.0
        if side == "BUY":
            entry_price = self._current_price + slippage_usd
        else:
            entry_price = self._current_price - slippage_usd

        commission = entry_price * self._lot_size * settings.commission_rate

        trade_id = self._next_id()
        trade = SimulatedTrade(
            id=trade_id,
            side=side,
            entry_price=entry_price,
            lot_size=self._lot_size,
            commission=commission,
            slippage=slippage_usd,
            latency_ms=latency_ms,
            signal_id=signal_id,
            signal_confidence=confidence,
            current_price=entry_price,
        )

        self._trades[trade_id] = trade
        log.info("Trade opened", id=trade_id, side=side, entry=entry_price)
        await self._emit_trade(trade)
        return trade

    async def close_trade(self, trade_id: int, reason: str = "MANUAL") -> Optional[SimulatedTrade]:
        trade = self._trades.get(trade_id)
        if not trade or trade.status != "OPEN":
            return None

        # Simulate exit slippage
        slippage_usd = self._current_price * settings.slippage_bps / 10000.0
        if trade.side == "BUY":
            exit_price = self._current_price - slippage_usd
            raw_pnl = (exit_price - trade.entry_price) * trade.lot_size
        else:
            exit_price = self._current_price + slippage_usd
            raw_pnl = (trade.entry_price - exit_price) * trade.lot_size

        exit_commission = exit_price * trade.lot_size * settings.commission_rate
        net_pnl = raw_pnl - trade.commission - exit_commission

        trade.exit_price = exit_price
        trade.pnl = net_pnl
        trade.exit_reason = reason
        trade.status = "CLOSED"
        trade.closed_at = time.time()
        trade.duration_seconds = trade.closed_at - trade.opened_at

        log.info("Trade closed", id=trade_id, pnl=net_pnl, reason=reason)
        await self._emit_trade(trade)
        return trade

    async def close_all(self, reason: str = "CLOSE_ALL"):
        open_trades = [t for t in self._trades.values() if t.status == "OPEN"]
        for trade in open_trades:
            await self.close_trade(trade.id, reason=reason)

    def _update_open_trades(self, price: float):
        for trade in self._trades.values():
            if trade.status != "OPEN":
                continue

            trade.current_price = price

            if trade.side == "BUY":
                excursion = (price - trade.entry_price) * trade.lot_size
            else:
                excursion = (trade.entry_price - price) * trade.lot_size

            trade.unrealized_pnl = excursion - trade.commission

            if excursion > trade.mfe:
                trade.mfe = excursion
            if excursion < trade.mae:
                trade.mae = excursion

            # Auto TP check
            if trade.unrealized_pnl >= settings.auto_tp_usd:
                asyncio.create_task(self.close_trade(trade.id, reason="AUTO_TP"))
            elif (time.time() - trade.opened_at) > settings.max_hold_seconds:
                asyncio.create_task(self.close_trade(trade.id, reason="MAX_HOLD"))

    async def _emit_trade(self, trade: SimulatedTrade):
        payload = self._trade_to_dict(trade)
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    cb(payload)
            except Exception as e:
                log.warning("Trade callback error", error=str(e))

    def _trade_to_dict(self, trade: SimulatedTrade) -> dict:
        return {
            "type": "trade_update",
            "id": trade.id,
            "side": trade.side,
            "entry_price": trade.entry_price,
            "exit_price": trade.exit_price,
            "lot_size": trade.lot_size,
            "commission": trade.commission,
            "slippage": trade.slippage,
            "latency_ms": trade.latency_ms,
            "pnl": trade.pnl,
            "unrealized_pnl": trade.unrealized_pnl,
            "mfe": trade.mfe,
            "mae": trade.mae,
            "status": trade.status,
            "exit_reason": trade.exit_reason,
            "signal_id": trade.signal_id,
            "signal_confidence": trade.signal_confidence,
            "opened_at": trade.opened_at,
            "closed_at": trade.closed_at,
            "duration_seconds": trade.duration_seconds,
        }

    def get_all_trades(self) -> list[dict]:
        return [self._trade_to_dict(t) for t in self._trades.values()]

    def get_open_trades(self) -> list[dict]:
        return [self._trade_to_dict(t) for t in self._trades.values() if t.status == "OPEN"]

    def get_closed_trades(self) -> list[dict]:
        return [self._trade_to_dict(t) for t in self._trades.values() if t.status == "CLOSED"]

    def get_performance(self) -> dict:
        closed = [t for t in self._trades.values() if t.status == "CLOSED"]
        if not closed:
            return {
                "total_trades": 0, "win_rate": 0.0, "avg_pnl": 0.0,
                "total_pnl": 0.0, "avg_hold_seconds": 0.0,
                "winning": 0, "losing": 0,
            }

        winners = [t for t in closed if t.pnl > 0]
        total_pnl = sum(t.pnl for t in closed)
        avg_hold = sum(t.duration_seconds for t in closed) / len(closed)

        return {
            "total_trades": len(closed),
            "win_rate": len(winners) / len(closed),
            "avg_pnl": total_pnl / len(closed),
            "total_pnl": total_pnl,
            "avg_hold_seconds": avg_hold,
            "winning": len(winners),
            "losing": len(closed) - len(winners),
        }

    def _next_id(self) -> int:
        self._trade_id_counter += 1
        return self._trade_id_counter

    def reset(self):
        self._trades.clear()
        self._trade_id_counter = 0
        log.info("ExecutionSimulator reset")


execution_simulator = ExecutionSimulatorService()

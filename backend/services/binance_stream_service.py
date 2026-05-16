"""
Connects to Binance WebSocket streams: aggTrade, depth20, bookTicker.
Computes real-time microstructure metrics across rolling windows.
"""
import asyncio
import json
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable, Optional
import websockets
import structlog

from config import settings

log = structlog.get_logger(__name__)


@dataclass
class Trade:
    timestamp: float
    price: float
    qty: float
    notional: float
    is_buyer_maker: bool  # True = seller aggressor, False = buyer aggressor


@dataclass
class OrderBookSnapshot:
    timestamp: float
    bids: list[tuple[float, float]]  # (price, qty)
    asks: list[tuple[float, float]]
    bid_total: float = 0.0
    ask_total: float = 0.0
    imbalance: float = 0.0          # (bid - ask) / (bid + ask)


@dataclass
class MicrostructureState:
    price: float = 0.0
    bid: float = 0.0
    ask: float = 0.0
    spread: float = 0.0

    # Per-window deltas (keyed by window seconds)
    agg_buy_delta: dict[int, float] = field(default_factory=dict)
    agg_sell_delta: dict[int, float] = field(default_factory=dict)
    net_delta: dict[int, float] = field(default_factory=dict)
    velocity: dict[int, float] = field(default_factory=dict)
    acceleration: dict[int, float] = field(default_factory=dict)

    # Global CVD
    cvd: float = 0.0

    # Order book
    imbalance: float = 0.0
    bid_total: float = 0.0
    ask_total: float = 0.0

    # Derived signals
    sweep_detected: bool = False
    absorption_detected: bool = False
    breakout_strength: float = 0.0
    continuation_prob: float = 0.0
    liquidity_pull_detected: bool = False

    # Raw aggression
    aggression_score: float = 0.0  # 0-1, buyer dominance

    timestamp: float = field(default_factory=time.time)


class BinanceStreamService:
    def __init__(self):
        self._trades: deque[Trade] = deque(maxlen=10000)
        self._prev_velocities: dict[int, deque[float]] = {
            w: deque(maxlen=30) for w in settings.windows
        }
        self._state = MicrostructureState()
        self._callbacks: list[Callable] = []
        self._running = False
        self._ws_task: Optional[asyncio.Task] = None
        self._cvd: float = 0.0
        self._last_velocity: dict[int, float] = {w: 0.0 for w in settings.windows}
        self._snapshot_task: Optional[asyncio.Task] = None

    @property
    def state(self) -> MicrostructureState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._running

    def subscribe(self, callback: Callable):
        self._callbacks.append(callback)

    async def start(self):
        if self._running:
            return
        self._running = True
        self._ws_task = asyncio.create_task(self._run_streams())
        self._snapshot_task = asyncio.create_task(self._compute_loop())
        log.info("BinanceStreamService started", symbol=settings.symbol)

    async def stop(self):
        self._running = False
        if self._ws_task:
            self._ws_task.cancel()
        if self._snapshot_task:
            self._snapshot_task.cancel()
        log.info("BinanceStreamService stopped")

    async def _run_streams(self):
        sym = settings.symbol.lower()
        streams = f"{sym}@aggTrade/{sym}@depth20@100ms/{sym}@bookTicker"
        url = f"{settings.binance_ws_base}?streams={streams}"

        while self._running:
            try:
                async with websockets.connect(
                    url,
                    ping_interval=20,
                    ping_timeout=10,
                    close_timeout=5,
                ) as ws:
                    log.info("Binance WS connected", url=url)
                    async for raw in ws:
                        if not self._running:
                            break
                        try:
                            msg = json.loads(raw)
                            await self._dispatch(msg)
                        except Exception as e:
                            log.warning("Dispatch error", error=str(e))
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    log.error("WS disconnected, reconnecting in 2s", error=str(e))
                    await asyncio.sleep(2)

    async def _dispatch(self, msg: dict):
        stream = msg.get("stream", "")
        data = msg.get("data", {})
        event = data.get("e", "")

        if event == "aggTrade":
            await self._handle_agg_trade(data)
        elif event == "depthUpdate" or "bids" in data:
            await self._handle_depth(data)
        elif event == "bookTicker":
            await self._handle_book_ticker(data)

    async def _handle_agg_trade(self, data: dict):
        price = float(data["p"])
        qty = float(data["q"])
        is_buyer_maker = data["m"]  # True = sell aggressor
        ts = data["T"] / 1000.0    # ms -> s

        notional = price * qty
        trade = Trade(
            timestamp=ts,
            price=price,
            qty=qty,
            notional=notional,
            is_buyer_maker=is_buyer_maker,
        )
        self._trades.append(trade)

        # Update CVD
        if not is_buyer_maker:  # buyer aggressor
            self._cvd += notional
        else:
            self._cvd -= notional

        self._state.price = price
        self._state.cvd = self._cvd

    async def _handle_depth(self, data: dict):
        bids = [(float(b[0]), float(b[1])) for b in data.get("bids", [])[:10]]
        asks = [(float(a[0]), float(a[1])) for a in data.get("asks", [])[:10]]

        bid_total = sum(p * q for p, q in bids)
        ask_total = sum(p * q for p, q in asks)
        total = bid_total + ask_total

        imbalance = (bid_total - ask_total) / total if total > 0 else 0.0

        self._state.bid_total = bid_total
        self._state.ask_total = ask_total
        self._state.imbalance = imbalance

        # Detect liquidity pull (sudden vanishing of one side)
        if abs(imbalance) > 0.75:
            self._state.liquidity_pull_detected = True
        else:
            self._state.liquidity_pull_detected = False

    async def _handle_book_ticker(self, data: dict):
        bid = float(data.get("b", 0))
        ask = float(data.get("a", 0))
        self._state.bid = bid
        self._state.ask = ask
        self._state.spread = ask - bid

    async def _compute_loop(self):
        """Compute rolling metrics every 100ms."""
        while self._running:
            try:
                await asyncio.sleep(0.1)
                now = time.time()
                self._compute_window_metrics(now)
                self._compute_derived_signals()
                self._state.timestamp = now
                await self._emit()
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("Compute loop error", error=str(e))

    def _compute_window_metrics(self, now: float):
        for w in settings.windows:
            cutoff = now - w
            buy_delta = 0.0
            sell_delta = 0.0

            for t in reversed(self._trades):
                if t.timestamp < cutoff:
                    break
                if not t.is_buyer_maker:
                    buy_delta += t.notional
                else:
                    sell_delta += t.notional

            self._state.agg_buy_delta[w] = buy_delta
            self._state.agg_sell_delta[w] = sell_delta
            self._state.net_delta[w] = buy_delta - sell_delta

            # Velocity = net delta / window seconds
            velocity = (buy_delta - sell_delta) / w
            prev_vel = self._last_velocity.get(w, 0.0)
            acceleration = (velocity - prev_vel) / 0.1  # per 100ms tick

            self._prev_velocities[w].append(velocity)
            self._last_velocity[w] = velocity
            self._state.velocity[w] = velocity
            self._state.acceleration[w] = acceleration

    def _compute_derived_signals(self):
        buy_1s = self._state.agg_buy_delta.get(1, 0.0)
        sell_1s = self._state.agg_sell_delta.get(1, 0.0)
        total_1s = buy_1s + sell_1s

        # Aggression score (buyer dominance 0-1)
        if total_1s > 0:
            self._state.aggression_score = buy_1s / total_1s
        else:
            self._state.aggression_score = 0.5

        # Sweep detection: very high velocity + strong imbalance
        vel_5s = self._state.velocity.get(5, 0.0)
        imbalance = self._state.imbalance
        self._state.sweep_detected = (
            abs(vel_5s) > settings.min_velocity_threshold * 3
            and abs(imbalance) > 0.6
        )

        # Absorption: high aggression but price not moving (approximation)
        self._state.absorption_detected = (
            total_1s > settings.min_delta_threshold * 0.5
            and abs(self._state.aggression_score - 0.5) < 0.1
        )

        # Continuation probability (simple heuristic, AI refines this)
        net_3s = self._state.net_delta.get(3, 0.0)
        net_5s = self._state.net_delta.get(5, 0.0)
        if net_3s != 0 and net_5s != 0:
            # Same direction and accelerating
            same_dir = (net_3s > 0) == (net_5s > 0)
            strength = min(abs(vel_5s) / (settings.min_velocity_threshold * 2), 1.0)
            self._state.continuation_prob = strength * 0.8 if same_dir else 0.2
        else:
            self._state.continuation_prob = 0.5

        # Breakout strength
        vel_10s = self._state.velocity.get(10, 0.0)
        self._state.breakout_strength = min(
            abs(vel_10s) / settings.min_velocity_threshold, 3.0
        )

    async def _emit(self):
        state_dict = self._state_to_dict()
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(state_dict)
                else:
                    cb(state_dict)
            except Exception as e:
                log.warning("Callback error", error=str(e))

    def _state_to_dict(self) -> dict:
        s = self._state
        return {
            "type": "market_update",
            "price": s.price,
            "bid": s.bid,
            "ask": s.ask,
            "spread": s.spread,
            "cvd": s.cvd,
            "imbalance": s.imbalance,
            "bid_total": s.bid_total,
            "ask_total": s.ask_total,
            "agg_buy_delta": s.agg_buy_delta,
            "agg_sell_delta": s.agg_sell_delta,
            "net_delta": s.net_delta,
            "velocity": s.velocity,
            "acceleration": s.acceleration,
            "sweep_detected": s.sweep_detected,
            "absorption_detected": s.absorption_detected,
            "liquidity_pull_detected": s.liquidity_pull_detected,
            "breakout_strength": s.breakout_strength,
            "continuation_prob": s.continuation_prob,
            "aggression_score": s.aggression_score,
            "timestamp": s.timestamp,
        }

    def get_recent_trades(self, seconds: float = 10.0) -> list[Trade]:
        cutoff = time.time() - seconds
        return [t for t in self._trades if t.timestamp >= cutoff]


binance_service = BinanceStreamService()

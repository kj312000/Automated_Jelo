"""
Replays stored market snapshots for strategy review and optimization.
"""
import asyncio
import time
from typing import Callable, Optional
import structlog

log = structlog.get_logger(__name__)


class ReplayService:
    def __init__(self):
        self._snapshots: list[dict] = []
        self._callbacks: list[Callable] = []
        self._playing = False
        self._speed = 1.0
        self._position = 0
        self._task: Optional[asyncio.Task] = None

    @property
    def is_playing(self) -> bool:
        return self._playing

    @property
    def position(self) -> int:
        return self._position

    @property
    def total(self) -> int:
        return len(self._snapshots)

    def subscribe(self, callback: Callable):
        self._callbacks.append(callback)

    def load_snapshots(self, snapshots: list[dict]):
        self._snapshots = sorted(snapshots, key=lambda x: x.get("timestamp", 0))
        self._position = 0
        log.info("Replay loaded", count=len(snapshots))

    async def play(self, speed: float = 1.0):
        if self._playing:
            return
        self._speed = max(0.1, min(speed, 50.0))
        self._playing = True
        self._task = asyncio.create_task(self._replay_loop())
        log.info("Replay started", speed=self._speed)

    async def pause(self):
        self._playing = False
        if self._task:
            self._task.cancel()
        log.info("Replay paused", position=self._position)

    def seek(self, position: int):
        self._position = max(0, min(position, len(self._snapshots) - 1))

    async def _replay_loop(self):
        while self._playing and self._position < len(self._snapshots):
            snap = self._snapshots[self._position]
            payload = {**snap, "type": "replay_update", "replay_position": self._position}

            for cb in self._callbacks:
                try:
                    if asyncio.iscoroutinefunction(cb):
                        await cb(payload)
                    else:
                        cb(payload)
                except Exception as e:
                    log.warning("Replay callback error", error=str(e))

            # Time between frames
            if self._position + 1 < len(self._snapshots):
                next_ts = self._snapshots[self._position + 1].get("timestamp", 0)
                curr_ts = snap.get("timestamp", 0)
                dt = (next_ts - curr_ts) / self._speed
                dt = max(0.001, min(dt, 2.0))  # clamp
                await asyncio.sleep(dt)

            self._position += 1

        self._playing = False
        log.info("Replay finished")


replay_service = ReplayService()

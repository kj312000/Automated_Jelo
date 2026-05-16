"""
WebSocket gateway: broadcasts all real-time events to connected frontend clients.
"""
import asyncio
import json
import time
from typing import Optional
import structlog
from fastapi import WebSocket, WebSocketDisconnect

log = structlog.get_logger(__name__)


class WebSocketGateway:
    def __init__(self):
        self._clients: set[WebSocket] = set()
        self._message_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._broadcast_task: Optional[asyncio.Task] = None

    @property
    def client_count(self) -> int:
        return len(self._clients)

    async def start(self):
        self._broadcast_task = asyncio.create_task(self._broadcast_loop())
        log.info("WebSocketGateway started")

    async def connect(self, ws: WebSocket):
        await ws.accept()
        self._clients.add(ws)
        log.info("WS client connected", total=len(self._clients))
        try:
            await ws.send_json({"type": "connected", "timestamp": time.time()})
        except Exception:
            pass

    async def disconnect(self, ws: WebSocket):
        self._clients.discard(ws)
        log.info("WS client disconnected", total=len(self._clients))

    async def broadcast(self, data: dict):
        try:
            self._message_queue.put_nowait(data)
        except asyncio.QueueFull:
            # Drop oldest
            try:
                self._message_queue.get_nowait()
                self._message_queue.put_nowait(data)
            except Exception:
                pass

    async def _broadcast_loop(self):
        while True:
            try:
                data = await self._message_queue.get()
                if not self._clients:
                    continue

                dead: set[WebSocket] = set()
                msg = json.dumps(data, default=str)

                await asyncio.gather(
                    *[self._send_one(ws, msg, dead) for ws in list(self._clients)],
                    return_exceptions=True,
                )

                for ws in dead:
                    await self.disconnect(ws)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Broadcast error", error=str(e))

    async def _send_one(self, ws: WebSocket, msg: str, dead: set):
        try:
            await asyncio.wait_for(ws.send_text(msg), timeout=1.0)
        except Exception:
            dead.add(ws)


ws_gateway = WebSocketGateway()

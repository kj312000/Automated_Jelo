"""
Real Exness MT5 execution engine.

All MT5 API calls are synchronous/blocking — run via run_in_executor to avoid
blocking the FastAPI event loop. Position monitor runs as a background async task.

Requires:
  - MetaTrader 5 terminal installed on this Windows machine
  - MT5_LOGIN, MT5_PASSWORD, MT5_SERVER in .env
  - MT5 symbol available on the account (default: ETHUSDm)
"""
import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from typing import Callable, Optional
import structlog

from config import settings

log = structlog.get_logger(__name__)

try:
    import MetaTrader5 as mt5
    MT5_AVAILABLE = True
except ImportError:
    MT5_AVAILABLE = False
    log.warning("MetaTrader5 package not importable")


@dataclass
class MT5Position:
    ticket: int
    side: str                    # BUY / SELL
    symbol: str
    volume: float
    entry_price: float
    current_price: float
    profit: float
    swap: float
    commission: float
    opened_at: float
    magic: int
    comment: str
    sl: float = 0.0
    tp: float = 0.0
    tp_amount: float = 0.0       # USD profit target for python monitor
    signal_id: Optional[int] = None
    signal_confidence: Optional[float] = None


class MT5ExecutionService:
    def __init__(self):
        self._connected = False
        self._enabled = False          # user toggle — live trades only when True
        self._auto_execute = False     # fire on signals automatically
        self._executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="mt5")
        self._monitor_task: Optional[asyncio.Task] = None
        self._callbacks: list[Callable] = []
        self._current_price: float = 0.0
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._positions: dict[int, MT5Position] = {}  # ticket → position
        self._active_symbol: str = settings.mt5_symbol  # resolved at connect time

    @property
    def active_symbol(self) -> str:
        return self._active_symbol

    # ── Properties ────────────────────────────────────────────────────────────

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_enabled(self) -> bool:
        return self._enabled

    @property
    def auto_execute(self) -> bool:
        return self._auto_execute

    # ── Lifecycle ─────────────────────────────────────────────────────────────

    def subscribe(self, callback: Callable):
        self._callbacks.append(callback)

    async def connect(self) -> dict:
        """Initialize MT5 and login. Returns status dict."""
        if not MT5_AVAILABLE:
            return {"ok": False, "error": "MetaTrader5 package not available"}

        if not settings.mt5_login or not settings.mt5_password or not settings.mt5_server:
            return {"ok": False, "error": "MT5_LOGIN / MT5_PASSWORD / MT5_SERVER not set in .env"}

        self._loop = asyncio.get_event_loop()
        result = await self._run(self._do_connect)
        if result["ok"]:
            self._connected = True
            self._monitor_task = asyncio.create_task(self._position_monitor())
            log.info("MT5 connected", account=settings.mt5_login, server=settings.mt5_server)
        else:
            log.error("MT5 connect failed", error=result.get("error"))
        return result

    def _do_connect(self) -> dict:
        kwargs = dict(
            login=settings.mt5_login,
            password=settings.mt5_password,
            server=settings.mt5_server,
        )
        if settings.mt5_terminal_path:
            kwargs["path"] = settings.mt5_terminal_path

        if not mt5.initialize(**kwargs):
            err = mt5.last_error()
            return {"ok": False, "error": f"initialize failed: {err}"}

        info = mt5.account_info()
        if info is None:
            return {"ok": False, "error": "account_info returned None — check credentials"}

        # Auto-discover symbol if configured one fails
        resolved_symbol = self._resolve_symbol(settings.mt5_symbol)
        if resolved_symbol is None:
            available = self._find_btc_symbols()
            return {
                "ok": False,
                "error": f"symbol_select failed for '{settings.mt5_symbol}'. "
                         f"Set MT5_SYMBOL in .env to one of: {available}",
                "available_eth_symbols": available,
            }

        # Update runtime symbol (doesn't persist to .env — user must update)
        self._active_symbol = resolved_symbol
        sym_info = mt5.symbol_info(resolved_symbol)

        return {
            "ok": True,
            "account": info.login,
            "name": info.name,
            "balance": info.balance,
            "equity": info.equity,
            "margin_free": info.margin_free,
            "currency": info.currency,
            "server": info.server,
            "symbol": resolved_symbol,
            "symbol_configured": settings.mt5_symbol,
            "symbol_auto_resolved": resolved_symbol != settings.mt5_symbol,
            "symbol_digits": sym_info.digits,
            "symbol_point": sym_info.point,
            "volume_min": sym_info.volume_min,
            "volume_step": sym_info.volume_step,
        }

    def _resolve_symbol(self, symbol: str) -> str | None:
        """Try the configured symbol then common Exness BTC/ETH variants."""
        candidates = [
            symbol,
            # BTC variants
            "BTCUSDm", "BTCUSD", "BTCUSDp", "BTCUSDr", "BTCUSDc",
            "BTCUSD.", "BTCUSD+", "BTCUSDx", "BTCUSDt", "XBTUSD",
            # ETH variants (fallback)
            "ETHUSDm", "ETHUSD", "ETHUSDp", "ETHUSDr", "ETHUSDc",
            "ETHUSD.", "ETHUSDx", "ETHUSDt",
        ]
        for s in candidates:
            if mt5.symbol_select(s, True):
                info = mt5.symbol_info(s)
                if info is not None:
                    log.info("MT5 symbol resolved", symbol=s)
                    return s
        return None

    def _find_btc_symbols(self) -> list[str]:
        """Return all BTC symbols visible on this account."""
        all_syms = mt5.symbols_get()
        if all_syms is None:
            return []
        return [s.name for s in all_syms if "BTC" in s.name.upper() or "XBT" in s.name.upper()]

    async def disconnect(self):
        self._connected = False
        self._enabled = False
        if self._monitor_task:
            self._monitor_task.cancel()
        await self._run(lambda: mt5.shutdown() if MT5_AVAILABLE else None)
        log.info("MT5 disconnected")

    def set_enabled(self, enabled: bool):
        self._enabled = enabled
        log.info("MT5 live trading", enabled=enabled)

    def set_auto_execute(self, enabled: bool):
        self._auto_execute = enabled
        log.info("MT5 auto-execute", enabled=enabled)

    def update_price(self, price: float):
        self._current_price = price

    # ── Signal handler ────────────────────────────────────────────────────────

    async def on_signal(self, signal: dict):
        if not self._auto_execute or not self._enabled or not self._connected:
            return

        confidence = signal.get("confidence", 0.0)
        if confidence < settings.min_confidence:
            return

        # Only one live position at a time
        if self._positions:
            return

        sig_type = signal.get("signal_type", "")
        if "LONG" in sig_type or sig_type == "ABSORPTION_REVERSAL":
            await self.open_position(
                "BUY",
                lot_size=settings.lot_size,
                signal_id=signal.get("id"),
                confidence=confidence,
            )
        elif "SHORT" in sig_type:
            await self.open_position(
                "SELL",
                lot_size=settings.lot_size,
                signal_id=signal.get("id"),
                confidence=confidence,
            )

    # ── Order execution ───────────────────────────────────────────────────────

    async def open_position(
        self,
        side: str,
        lot_size: Optional[float] = None,
        signal_id: Optional[int] = None,
        confidence: Optional[float] = None,
        sl_override: Optional[float] = None,
        tp_override: Optional[float] = None,
    ) -> dict:
        if not self._connected or not self._enabled:
            return {"ok": False, "error": "MT5 not connected or not enabled"}

        volume = lot_size or settings.lot_size
        sl_usd = sl_override or settings.sl_usd_per_lot
        tp_usd = tp_override or settings.tp_usd_per_lot
        result = await self._run(lambda: self._do_open(side, volume, signal_id, confidence, sl_usd, tp_usd))

        if result.get("ok"):
            ticket = result["ticket"]
            pos = MT5Position(
                ticket=ticket,
                side=side,
                symbol=self._active_symbol,
                volume=volume,
                entry_price=result["price"],
                current_price=result["price"],
                profit=0.0,
                swap=0.0,
                commission=result.get("commission", 0.0),
                opened_at=time.time(),
                magic=settings.mt5_magic,
                comment=f"BTC-MST sig#{signal_id}",
                sl=result.get("sl", 0.0),
                tp=result.get("tp", 0.0),
                tp_amount=tp_usd,
                signal_id=signal_id,
                signal_confidence=confidence,
            )
            self._positions[ticket] = pos
            await self._emit_position(pos, "OPEN")
            log.info("MT5 position opened", ticket=ticket, side=side, price=result["price"])
        else:
            log.error("MT5 open failed", error=result.get("error"))
            await self._emit_error(result.get("error", "unknown"))

        return result

    def _do_open(self, side: str, volume: float, signal_id, confidence, sl_usd: float, tp_usd: float) -> dict:
        sym = self._active_symbol
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            return {"ok": False, "error": f"no tick for {sym}"}

        order_type = mt5.ORDER_TYPE_BUY if side == "BUY" else mt5.ORDER_TYPE_SELL
        price = tick.ask if side == "BUY" else tick.bid

        if side == "BUY":
            sl = round(price - sl_usd, 2)
            tp = round(price + tp_usd, 2)
        else:
            sl = round(price + sl_usd, 2)
            tp = round(price - tp_usd, 2)

        sym_info = mt5.symbol_info(sym)
        if sym_info:
            volume = max(sym_info.volume_min, round(volume / sym_info.volume_step) * sym_info.volume_step)

        conf_str = f"{confidence:.2f}" if confidence is not None else "n/a"
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": volume,
            "type": order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": settings.mt5_deviation,
            "magic": settings.mt5_magic,
            "comment": f"BTC-MST sig#{signal_id} conf={conf_str}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            return {"ok": False, "error": f"order_send returned None: {err}"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            if result.retcode == 10027:
                err = "AutoTrading disabled — click 'Algo Trading' button in MT5 toolbar"
            else:
                err = f"retcode={result.retcode} {result.comment}"
            return {"ok": False, "error": err, "retcode": result.retcode}

        return {
            "ok": True,
            "ticket": result.order,
            "price": result.price,
            "sl": sl,
            "tp": tp,
            "volume": result.volume,
            "commission": getattr(result, "commission", 0.0),
            "retcode": result.retcode,
        }

    async def close_position(self, ticket: int, reason: str = "MANUAL") -> dict:
        if not self._connected:
            return {"ok": False, "error": "not connected"}

        pos = self._positions.get(ticket)
        if not pos:
            return {"ok": False, "error": f"ticket {ticket} not tracked"}

        result = await self._run(lambda: self._do_close(ticket, pos))

        if result.get("ok"):
            pos.profit = result.get("profit", pos.profit)
            await self._emit_position(pos, reason)
            del self._positions[ticket]
            log.info("MT5 position closed", ticket=ticket, reason=reason, profit=pos.profit)
        else:
            log.error("MT5 close failed", ticket=ticket, error=result.get("error"))

        return result

    def _do_close(self, ticket: int, pos: MT5Position) -> dict:
        sym = self._active_symbol
        tick = mt5.symbol_info_tick(sym)
        if tick is None:
            return {"ok": False, "error": f"no tick for {sym}"}

        # Opposite side to close
        close_type = mt5.ORDER_TYPE_SELL if pos.side == "BUY" else mt5.ORDER_TYPE_BUY
        close_price = tick.bid if pos.side == "BUY" else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": sym,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": close_price,
            "deviation": settings.mt5_deviation,
            "magic": settings.mt5_magic,
            "comment": "BTC-MST close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            return {"ok": False, "error": f"order_send None: {err}"}

        if result.retcode != mt5.TRADE_RETCODE_DONE:
            return {
                "ok": False,
                "error": f"retcode={result.retcode} {result.comment}",
                "retcode": result.retcode,
            }

        return {"ok": True, "price": result.price, "profit": result.profit, "retcode": result.retcode}

    async def close_all(self, reason: str = "CLOSE_ALL") -> list[dict]:
        results = []
        for ticket in list(self._positions.keys()):
            r = await self.close_position(ticket, reason=reason)
            results.append(r)
        return results

    # ── Position monitor ──────────────────────────────────────────────────────

    async def _position_monitor(self):
        """Poll MT5 for live P&L and trigger auto-close conditions."""
        while self._connected:
            try:
                await asyncio.sleep(settings.mt5_poll_interval)
                if not self._positions:
                    continue

                updates = await self._run(self._fetch_positions)

                for ticket, pdata in updates.items():
                    pos = self._positions.get(ticket)
                    if not pos:
                        continue

                    pos.current_price = pdata["price"]
                    pos.profit = pdata["profit"]
                    pos.swap = pdata["swap"]
                    pos.commission = pdata["commission"]

                    await self._emit_position(pos, "UPDATE")

                    # Auto-close conditions (use per-position adaptive TP if set)
                    hold_seconds = time.time() - pos.opened_at
                    tp_target = pos.tp_amount if pos.tp_amount > 0 else settings.tp_usd_per_lot
                    if pos.profit >= tp_target:
                        asyncio.create_task(self.close_position(ticket, "AUTO_TP"))
                    elif hold_seconds >= settings.max_hold_seconds:
                        asyncio.create_task(self.close_position(ticket, "MAX_HOLD"))

                # Detect externally closed positions (closed from MT5 terminal)
                tracked = set(self._positions.keys())
                live = set(updates.keys())
                for ghost in tracked - live:
                    pos = self._positions.pop(ghost, None)
                    if pos:
                        await self._emit_position(pos, "CLOSED_EXTERNAL")
                        log.info("MT5 position closed externally", ticket=ghost)

            except asyncio.CancelledError:
                break
            except Exception as e:
                log.warning("MT5 monitor error", error=str(e))

    def _fetch_positions(self) -> dict:
        """Blocking MT5 call — runs in executor."""
        raw = mt5.positions_get(symbol=self._active_symbol, magic=settings.mt5_magic)
        if raw is None:
            return {}
        result = {}
        for p in raw:
            result[p.ticket] = {
                "price": p.price_current,
                "profit": p.profit,
                "swap": p.swap,
                "commission": p.commission,
            }
        return result

    # ── Account info ──────────────────────────────────────────────────────────

    async def get_account_info(self) -> dict:
        if not self._connected:
            return {"ok": False, "error": "not connected"}
        return await self._run(self._do_account_info)

    def _do_account_info(self) -> dict:
        info = mt5.account_info()
        if info is None:
            return {"ok": False, "error": "account_info None"}
        return {
            "ok": True,
            "login": info.login,
            "name": info.name,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "margin_free": info.margin_free,
            "margin_level": info.margin_level,
            "profit": info.profit,
            "currency": info.currency,
            "leverage": info.leverage,
            "server": info.server,
        }

    async def get_positions(self) -> list[dict]:
        return [self._pos_to_dict(p) for p in self._positions.values()]

    def get_positions_sync(self) -> list[dict]:
        return [self._pos_to_dict(p) for p in self._positions.values()]

    # ── Emit helpers ──────────────────────────────────────────────────────────

    async def _emit_position(self, pos: MT5Position, event: str):
        payload = {
            "type": "mt5_position",
            "event": event,
            **self._pos_to_dict(pos),
        }
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    cb(payload)
            except Exception as e:
                log.warning("MT5 callback error", error=str(e))

    async def _emit_error(self, error: str):
        payload = {"type": "mt5_error", "error": error, "timestamp": time.time()}
        for cb in self._callbacks:
            try:
                if asyncio.iscoroutinefunction(cb):
                    await cb(payload)
                else:
                    cb(payload)
            except Exception:
                pass

    def _pos_to_dict(self, pos: MT5Position) -> dict:
        now = time.time()
        return {
            "ticket": pos.ticket,
            "side": pos.side,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "entry_price": pos.entry_price,
            "current_price": pos.current_price,
            "profit": pos.profit,
            "swap": pos.swap,
            "commission": pos.commission,
            "hold_seconds": now - pos.opened_at,
            "opened_at": pos.opened_at,
            "sl": pos.sl,
            "tp": pos.tp,
            "magic": pos.magic,
            "comment": pos.comment,
            "signal_id": pos.signal_id,
            "signal_confidence": pos.signal_confidence,
            "timestamp": now,
        }

    # ── Utility ───────────────────────────────────────────────────────────────

    async def _run(self, fn):
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(self._executor, fn)


mt5_service = MT5ExecutionService()

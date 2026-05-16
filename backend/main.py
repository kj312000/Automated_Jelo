"""
BTC Microstructure Terminal — FastAPI backend.
Signal pipeline: Binance → signal engine → AI bias check → signal queue → MT5 execute.
"""
import asyncio
import time
from contextlib import asynccontextmanager

# ── Logging must be configured before any local imports create loggers ────────
from logging_config import setup_logging
setup_logging()

import structlog
import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from config import settings
from database.db import init_db
from websocket_gateway import ws_gateway
from services.binance_stream_service import binance_service
from services.signal_engine_service import signal_engine
from services.mt5_execution_service import mt5_service
from services.ai_analysis_service import ai_service
from services.analytics_service import analytics_service
from services.replay_service import replay_service
from services.risk_manager import risk_manager
from services.trade_logger import trade_logger
from services import config_store
from services.signal_queue_service import signal_queue_service

log = structlog.get_logger(__name__)

# ── Module-level state ────────────────────────────────────────────────────────

# Carries signal + evaluation from on_signal → on_mt5_event("OPEN")
_pending_open_ctx: dict = {}

# Executor heartbeat — local Windows MT5 process pings this
_executor_hb: dict = {"last_seen": 0.0, "executor_id": "", "version": ""}

# ── Weakness monitor ──────────────────────────────────────────────────────────

_weakness_task: asyncio.Task | None = None


async def _weakness_monitor():
    """While MT5 has open positions, ask AI if we should exit early."""
    while True:
        try:
            await asyncio.sleep(3.0)
            if not mt5_service.is_connected or not mt5_service._positions:
                continue
            market = binance_service._state_to_dict()
            for ticket, pos in list(mt5_service._positions.items()):
                pos_dict = mt5_service._pos_to_dict(pos)
                result = await ai_service.check_trade_weakness(pos_dict, market)
                if result.get("exit_now"):
                    reason = result.get("reason", "AI_WEAKNESS")
                    log.info("AI weakness exit", ticket=ticket, reason=reason)
                    await mt5_service.close_position(ticket, reason="AI_WEAKNESS")
                    await ws_gateway.broadcast({
                        "type": "system_event",
                        "event": "ai_weakness_exit",
                        "ticket": ticket,
                        "reason": reason,
                        "timestamp": time.time(),
                    })
        except asyncio.CancelledError:
            break
        except Exception as e:
            log.warning("Weakness monitor error", error=str(e))

# ── Lifespan ──────────────────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    global _weakness_task
    await init_db()

    # Restore runtime config from DB (survives redeploys)
    await config_store.load_and_apply(settings, ai_service)

    async def on_market_update(market: dict):
        risk_manager.update(market)
        mt5_service.update_price(market.get("price", 0.0))
        signal = await signal_engine.process(market)

        ai_service.update_context(
            market,
            mt5_service.get_positions_sync(),
            signal_engine.get_recent_signals(20),
        )
        await ws_gateway.broadcast(market)

    async def on_signal(signal: dict):
        # ── Risk manager evaluation ───────────────────────────────────────────
        market = binance_service._state_to_dict()
        evaluation = risk_manager.evaluate_signal(signal, market)
        signal["quality_score"]  = evaluation["quality_score"]
        signal["breakout_phase"] = evaluation["breakout_phase"]
        signal["regime"]         = evaluation["regime"]

        # Feed AI batch accumulator
        ai_service.add_signal(signal)

        # Attach bias for frontend
        bias = ai_service.current_bias
        signal["ai_bias"] = bias
        signal["ai_bias_reason"] = ai_service.bias_reason
        await ws_gateway.broadcast(signal)

        # Risk manager gate
        if not evaluation["allowed"]:
            skip = evaluation.get("skip_reason", "risk_manager")
            log.info("Signal skipped — risk_manager",
                     reason=skip, signal_type=signal.get("signal_type"))
            asyncio.create_task(
                trade_logger.log_signal(signal, evaluation, bias, executed=False))
            await ws_gateway.broadcast({
                "type": "system_event", "event": "signal_skipped",
                "reason": skip, "signal_type": signal.get("signal_type"),
                "timestamp": time.time(),
            })
            return

        sig_type = signal.get("signal_type", "")
        is_long  = "LONG" in sig_type or sig_type == "ABSORPTION_REVERSAL"
        is_short = "SHORT" in sig_type

        # Bias gate — PAUSE
        if bias == "PAUSE":
            log.info("Signal skipped — AI bias=PAUSE", signal_type=sig_type)
            asyncio.create_task(
                trade_logger.log_signal(signal, evaluation, bias, executed=False))
            await ws_gateway.broadcast({
                "type": "system_event", "event": "signal_skipped",
                "reason": f"AI bias=PAUSE: {ai_service.bias_reason}",
                "signal_type": sig_type, "timestamp": time.time(),
            })
            return

        # Global kill switch gate
        if not settings.global_trading_enabled:
            log.warning("Signal blocked — global kill switch active",
                        signal_type=sig_type)
            asyncio.create_task(
                trade_logger.log_signal(signal, evaluation, bias, executed=False))
            await ws_gateway.broadcast({
                "type": "system_event", "event": "signal_skipped",
                "reason": "Kill switch active", "signal_type": sig_type,
                "timestamp": time.time(),
            })
            return

        # Bias direction gate
        if bias == "LONG" and not is_long:
            asyncio.create_task(
                trade_logger.log_signal(signal, evaluation, bias, executed=False))
            return
        if bias == "SHORT" and not is_short:
            asyncio.create_task(
                trade_logger.log_signal(signal, evaluation, bias, executed=False))
            return

        # ── Execute ───────────────────────────────────────────────────────────
        params = risk_manager.get_adaptive_params()
        side = "BUY" if is_long else ("SELL" if is_short else None)
        executed = False

        if side:
            # Enqueue for remote/local executor (always — audit trail + Railway support)
            asyncio.create_task(
                signal_queue_service.enqueue(signal, side, params.sl, params.tp))

            # Direct MT5 execution when connected locally
            if mt5_service.is_connected and mt5_service.is_enabled and mt5_service.auto_execute:
                if not mt5_service._positions:
                    _pending_open_ctx.update({
                        "signal": signal,
                        "evaluation": evaluation,
                        "sl": params.sl,
                        "tp": params.tp,
                    })
                    result = await mt5_service.open_position(
                        side,
                        lot_size=settings.lot_size,
                        signal_id=signal.get("id"),
                        confidence=signal.get("confidence"),
                        sl_override=params.sl,
                        tp_override=params.tp,
                    )
                    executed = result.get("ok", False)
                    if executed:
                        direction = "LONG" if side == "BUY" else "SHORT"
                        risk_manager.record_execution(direction)
                    else:
                        _pending_open_ctx.clear()

        asyncio.create_task(
            trade_logger.log_signal(signal, evaluation, bias, executed=executed))

    async def on_mt5_event(data: dict):
        event = data.get("event", "")
        ticket = data.get("ticket")

        if event == "OPEN":
            ctx = _pending_open_ctx.copy()
            _pending_open_ctx.clear()
            asyncio.create_task(trade_logger.log_trade_open(
                mt5_ticket=ticket,
                side=data.get("side", ""),
                symbol=data.get("symbol", ""),
                entry_price=data.get("entry_price", 0.0),
                lot_size=data.get("volume", settings.lot_size),
                commission=data.get("commission", 0.0),
                signal=ctx.get("signal"),
                evaluation=ctx.get("evaluation"),
                adaptive_sl=ctx.get("sl"),
                adaptive_tp=ctx.get("tp"),
            ))

        close_events = {"AUTO_TP", "MAX_HOLD", "MANUAL", "SL_HIT", "AI_WEAKNESS", "CLOSED_EXTERNAL"}
        if event in close_events:
            profit = data.get("profit", 0.0)
            asyncio.create_task(trade_logger.log_trade_close(
                mt5_ticket=ticket,
                exit_price=data.get("current_price", 0.0),
                pnl=profit,
                swap=data.get("swap", 0.0),
                exit_reason=event,
                duration_seconds=data.get("hold_seconds", 0.0),
            ))
            risk_manager.record_result(
                profit=profit,
                signal_type=data.get("signal_type", ""),
                session=risk_manager.current_session,
                regime=risk_manager.current_regime,
            )
            market = binance_service._state_to_dict()
            asyncio.create_task(ai_service.analyze_trade(data, market))

        await ws_gateway.broadcast(data)

    async def on_ai(data: dict):
        await ws_gateway.broadcast(data)

    binance_service.subscribe(on_market_update)
    signal_engine.subscribe(on_signal)
    mt5_service.subscribe(on_mt5_event)
    ai_service.subscribe(on_ai)

    await ws_gateway.start()
    await ai_service.start()
    _weakness_task = asyncio.create_task(_weakness_monitor())
    log.info("BTC-MST backend started")

    yield

    if _weakness_task:
        _weakness_task.cancel()
    await binance_service.stop()
    await ai_service.stop()
    if mt5_service.is_connected:
        await mt5_service.disconnect()
    log.info("Shutdown complete")


# ── App ───────────────────────────────────────────────────────────────────────

app = FastAPI(title="BTC-MST", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── WebSocket ─────────────────────────────────────────────────────────────────

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws_gateway.connect(ws)
    try:
        while True:
            try:
                await asyncio.wait_for(ws.receive_text(), timeout=30.0)
            except asyncio.TimeoutError:
                pass
    except WebSocketDisconnect:
        pass
    finally:
        await ws_gateway.disconnect(ws)

# ── Flow control ──────────────────────────────────────────────────────────────

@app.post("/api/flow/start")
async def start_flow():
    signal_engine.start()
    await binance_service.start()
    return {"status": "started"}

@app.post("/api/flow/stop")
async def stop_flow():
    await binance_service.stop()
    return {"status": "stopped"}

@app.post("/api/flow/pause-signals")
async def pause_signals():
    signal_engine.pause()
    return {"status": "paused"}

@app.post("/api/flow/resume-signals")
async def resume_signals():
    signal_engine.resume()
    return {"status": "resumed"}

# ── Status ────────────────────────────────────────────────────────────────────

@app.get("/api/status")
async def get_status():
    risk = risk_manager.status_dict()
    return {
        "binance_connected": binance_service.is_running,
        "signal_engine_running": signal_engine.is_running,
        "signal_engine_paused": signal_engine.is_paused,
        "ai_running": ai_service.is_running,
        "ai_signals_enabled": ai_service.signals_enabled,
        "ai_weakness_enabled": ai_service.weakness_enabled,
        "ai_threshold": ai_service.confidence_threshold,
        "ai_bias": ai_service.current_bias,
        "ai_bias_reason": ai_service.bias_reason,
        "mt5_connected": mt5_service.is_connected,
        "mt5_enabled": mt5_service.is_enabled,
        "mt5_auto_execute": mt5_service.auto_execute,
        "mt5_symbol": mt5_service.active_symbol,
        "ws_clients": ws_gateway.client_count,
        "regime": risk["regime"],
        "session": risk["session"],
        "exec_health": risk["exec_health"],
        "exec_spread_ratio": risk["exec_spread_ratio"],
        "cooldown": risk["cooldown"],
        "adaptive": risk["adaptive"],
        "consecutive_losses": risk["consecutive_losses"],
        "tradeable": risk["tradeable"],
        # Executor heartbeat
        "executor_online": time.time() - _executor_hb["last_seen"] < 30,
        "executor_last_seen": _executor_hb["last_seen"],
        "executor_id": _executor_hb["executor_id"],
        # Kill switch
        "global_trading_enabled": settings.global_trading_enabled,
        "timestamp": time.time(),
    }

@app.get("/api/market")
async def get_market():
    return binance_service._state_to_dict()

# ── MT5 ───────────────────────────────────────────────────────────────────────

@app.post("/api/mt5/connect")
async def mt5_connect():
    result = await mt5_service.connect()
    if not result.get("ok"):
        raise HTTPException(400, detail=result)
    return result

@app.post("/api/mt5/disconnect")
async def mt5_disconnect():
    await mt5_service.disconnect()
    return {"status": "disconnected"}

@app.post("/api/mt5/enable")
async def mt5_enable(enabled: bool):
    mt5_service.set_enabled(enabled)
    return {"enabled": enabled}

@app.post("/api/mt5/auto-execute")
async def mt5_auto_execute(enabled: bool):
    mt5_service.set_auto_execute(enabled)
    return {"auto_execute": enabled}

@app.get("/api/mt5/account")
async def mt5_account():
    return await mt5_service.get_account_info()

@app.get("/api/mt5/positions")
async def mt5_positions():
    return await mt5_service.get_positions()

class MT5TradeRequest(BaseModel):
    side: str
    lot_size: float | None = None

@app.post("/api/mt5/trade/open")
async def mt5_open(req: MT5TradeRequest):
    result = await mt5_service.open_position(
        req.side.upper(),
        lot_size=req.lot_size or settings.lot_size,
    )
    if not result.get("ok"):
        raise HTTPException(400, result.get("error"))
    return result

@app.post("/api/mt5/trade/{ticket}/close")
async def mt5_close(ticket: int):
    result = await mt5_service.close_position(ticket, reason="MANUAL")
    if not result.get("ok"):
        raise HTTPException(400, result.get("error"))
    return result

@app.post("/api/mt5/trade/close-all")
async def mt5_close_all():
    results = await mt5_service.close_all("MANUAL_ALL")
    return {"closed": len(results)}

@app.get("/api/mt5/symbols/search")
async def mt5_symbols_search(query: str = "BTC"):
    if not mt5_service.is_connected:
        raise HTTPException(400, "MT5 not connected")
    def _search():
        import MetaTrader5 as mt5_mod
        syms = mt5_mod.symbols_get()
        if syms is None:
            return []
        q = query.upper()
        return [{"name": s.name, "description": s.description, "volume_min": s.volume_min}
                for s in syms if q in s.name.upper()]
    loop = asyncio.get_event_loop()
    from concurrent.futures import ThreadPoolExecutor
    with ThreadPoolExecutor(max_workers=1) as ex:
        results = await loop.run_in_executor(ex, _search)
    return {"symbols": results}

@app.get("/api/mt5/symbol/active")
async def mt5_active_symbol():
    return {"configured": settings.mt5_symbol, "active": mt5_service.active_symbol}

# ── Signals ───────────────────────────────────────────────────────────────────

@app.get("/api/signals")
async def get_signals(limit: int = 20):
    return signal_engine.get_recent_signals(limit)

# ── Analytics ─────────────────────────────────────────────────────────────────

@app.get("/api/analytics")
async def get_analytics():
    positions = mt5_service.get_positions_sync()
    return analytics_service.compute_metrics(positions)

# ── AI ────────────────────────────────────────────────────────────────────────

@app.post("/api/ai/analyze")
async def ai_analyze():
    market = binance_service._state_to_dict()
    positions = mt5_service.get_positions_sync()
    signals = signal_engine.get_recent_signals(5)
    ai_service.update_context(market, positions, signals)
    await ai_service._run_market_analysis()
    return {"status": "triggered"}

@app.get("/api/ai/threshold")
async def ai_threshold():
    return {"threshold": ai_service.confidence_threshold}

@app.post("/api/ai/threshold")
async def set_ai_threshold(value: float):
    ai_service.confidence_threshold = max(0.55, min(0.90, value))
    return {"threshold": ai_service.confidence_threshold}

@app.get("/api/ai/bias")
async def ai_bias_get():
    return {"bias": ai_service.current_bias, "reason": ai_service.bias_reason}

@app.post("/api/ai/bias")
async def ai_bias_set(bias: str):
    bias = bias.upper()
    if bias not in {"LONG", "SHORT", "BOTH", "PAUSE"}:
        raise HTTPException(400, "bias must be LONG|SHORT|BOTH|PAUSE")
    ai_service._current_bias = bias
    return {"bias": bias}

@app.get("/api/ai/enabled")
async def ai_enabled_get():
    return {
        "signals_enabled": ai_service.signals_enabled,
        "weakness_enabled": ai_service.weakness_enabled,
    }

@app.post("/api/ai/signals-enabled")
async def ai_signals_enabled_set(enabled: bool):
    ai_service.signals_enabled = enabled
    asyncio.create_task(config_store.save("ai_signals_enabled", enabled))
    log.info("AI signals analysis toggled", enabled=enabled)
    return {"signals_enabled": enabled}

@app.post("/api/ai/weakness-enabled")
async def ai_weakness_enabled_set(enabled: bool):
    ai_service.weakness_enabled = enabled
    asyncio.create_task(config_store.save("ai_weakness_enabled", enabled))
    log.info("AI weakness monitor toggled", enabled=enabled)
    return {"weakness_enabled": enabled}

# ── Logs ──────────────────────────────────────────────────────────────────────

@app.get("/api/logs/signals")
async def log_signals(limit: int = 50):
    return await trade_logger.get_recent_signals(limit)

@app.get("/api/logs/trades")
async def log_trades(limit: int = 50):
    return await trade_logger.get_recent_trades(limit)

# ── Executor heartbeat + signal queue ─────────────────────────────────────────

@app.post("/api/executor/heartbeat")
async def executor_heartbeat(executor_id: str = "", version: str = ""):
    _executor_hb.update({
        "last_seen": time.time(),
        "executor_id": executor_id,
        "version": version,
    })
    # Expire stale queue entries on every heartbeat
    asyncio.create_task(signal_queue_service.expire_old())
    return {"ok": True, "server_time": time.time()}

@app.get("/api/executor/queue")
async def executor_queue_pending():
    """Local executor polls this for PENDING signals to execute."""
    return await signal_queue_service.get_pending()

@app.get("/api/executor/queue/recent")
async def executor_queue_recent(limit: int = 50):
    return await signal_queue_service.get_recent(limit)

class AckRequest(BaseModel):
    status: str           # EXECUTED | FAILED
    mt5_ticket: int | None = None
    error: str = ""

@app.post("/api/executor/queue/{queue_id}/ack")
async def executor_queue_ack(queue_id: int, req: AckRequest):
    ok = await signal_queue_service.ack(
        queue_id, req.status, req.error, req.mt5_ticket
    )
    if not ok:
        raise HTTPException(404, "Queue entry not found")
    return {"ok": True}

# ── Global kill switch ────────────────────────────────────────────────────────

@app.get("/api/trading/status")
async def trading_status():
    return {"global_trading_enabled": settings.global_trading_enabled}

@app.post("/api/trading/kill")
async def trading_kill():
    object.__setattr__(settings, "global_trading_enabled", False)
    asyncio.create_task(config_store.save("global_trading_enabled", False))
    log.warning("KILL SWITCH ACTIVATED — all new executions blocked")
    await ws_gateway.broadcast({
        "type": "system_event", "event": "kill_switch",
        "enabled": False, "timestamp": time.time(),
    })
    return {"global_trading_enabled": False}

@app.post("/api/trading/resume")
async def trading_resume():
    object.__setattr__(settings, "global_trading_enabled", True)
    asyncio.create_task(config_store.save("global_trading_enabled", True))
    log.info("Trading resumed — kill switch cleared")
    await ws_gateway.broadcast({
        "type": "system_event", "event": "kill_switch",
        "enabled": True, "timestamp": time.time(),
    })
    return {"global_trading_enabled": True}

# ── Config ────────────────────────────────────────────────────────────────────

@app.get("/api/config")
async def get_config():
    return {
        "lot_size": settings.lot_size,
        "tp_usd": settings.tp_usd_per_lot,
        "sl_usd": settings.sl_usd_per_lot,
        "rr_ratio": round(settings.tp_usd_per_lot / settings.sl_usd_per_lot, 2),
        "max_hold_seconds": settings.max_hold_seconds,
        "symbol": settings.symbol,
        "mt5_symbol": settings.mt5_symbol,
        "ai_batch_size": settings.ai_batch_size,
    }

_MUTABLE_KEYS: set[str] = {
    "min_confidence",
    "lot_size",
    "tp_usd_per_lot",
    "sl_usd_per_lot",
    "max_hold_seconds",
    "signal_cooldown_seconds",
    "signal_type_cooldown_seconds",
    "min_quality_score",
    "ai_batch_size",
    "ai_batch_interval",
    "ai_analysis_interval",
    "min_delta_threshold",
    "min_velocity_threshold",
    "max_ai_calls_per_minute",
    "cooldown_between_same_direction_signals",
    "signal_queue_expiry_seconds",
}

@app.get("/api/config/runtime")
async def get_runtime_config():
    return {k: getattr(settings, k) for k in sorted(_MUTABLE_KEYS)}

@app.post("/api/config/runtime")
async def set_runtime_config(updates: dict):
    changed = {}
    for k, v in updates.items():
        if k not in _MUTABLE_KEYS:
            continue
        try:
            current = getattr(settings, k)
            coerced = type(current)(v)
            object.__setattr__(settings, k, coerced)
            changed[k] = coerced
            log.info("Config updated", key=k, value=coerced)
        except Exception as exc:
            log.warning("Config update failed", key=k, error=str(exc))
    # Sync derived values
    if "min_confidence" in changed:
        ai_service.confidence_threshold = changed["min_confidence"]
    # Persist to DB so change survives redeploy
    if changed:
        asyncio.create_task(config_store.save_bulk(changed))
    return changed


if __name__ == "__main__":
    uvicorn.run("main:app", host=settings.host, port=settings.port, reload=settings.debug)

from sqlalchemy import Column, Integer, Float, String, Boolean, DateTime, Text, JSON
from sqlalchemy.orm import DeclarativeBase
from datetime import datetime


class Base(DeclarativeBase):
    pass


class Trade(Base):
    __tablename__ = "trades"

    id = Column(Integer, primary_key=True, autoincrement=True)
    mt5_ticket = Column(Integer, nullable=True, index=True)   # MT5 order ticket
    mt5_symbol = Column(String(16), nullable=True)
    side = Column(String(4), nullable=False)                  # BUY / SELL
    entry_price = Column(Float, nullable=False)
    exit_price = Column(Float, nullable=True)
    lot_size = Column(Float, nullable=False)
    commission = Column(Float, default=0.0)
    swap = Column(Float, default=0.0)
    slippage = Column(Float, default=0.0)
    latency_ms = Column(Float, default=0.0)
    pnl = Column(Float, nullable=True)
    mfe = Column(Float, default=0.0)                          # max favorable excursion
    mae = Column(Float, default=0.0)                          # max adverse excursion
    status = Column(String(8), default="OPEN")                # OPEN / CLOSED
    exit_reason = Column(String(32), nullable=True)
    signal_id = Column(Integer, nullable=True)
    signal_confidence = Column(Float, nullable=True)
    signal_quality_score = Column(Integer, nullable=True)
    signal_breakout_phase = Column(String(16), nullable=True)
    regime = Column(String(20), nullable=True)                # volatility regime at entry
    session = Column(String(16), nullable=True)               # trading session at entry
    adaptive_sl = Column(Float, nullable=True)                # SL used (adaptive)
    adaptive_tp = Column(Float, nullable=True)                # TP used (adaptive)
    duration_seconds = Column(Float, nullable=True)
    opened_at = Column(DateTime, default=datetime.utcnow)
    closed_at = Column(DateTime, nullable=True)
    metadata_ = Column("metadata", JSON, default=dict)


class Signal(Base):
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_type = Column(String(32), nullable=False)
    confidence = Column(Float, nullable=False)
    continuation_prob = Column(Float, nullable=False)
    velocity_score = Column(Float, nullable=False)
    delta_score = Column(Float, nullable=False)
    imbalance_score = Column(Float, nullable=False)
    aggression_score = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    trigger_reason = Column(Text, nullable=False)
    quality_score = Column(Integer, nullable=True)
    breakout_phase = Column(String(16), nullable=True)
    regime = Column(String(20), nullable=True)
    session = Column(String(16), nullable=True)
    ai_bias = Column(String(8), nullable=True)
    executed = Column(Boolean, default=False)    # fired MT5 order
    skipped = Column(Boolean, default=False)     # blocked by gate
    skip_reason = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class AIAnalysis(Base):
    __tablename__ = "ai_analysis"

    id = Column(Integer, primary_key=True, autoincrement=True)
    analysis_type = Column(String(32), nullable=False)  # MARKET / TRADE / IMPROVEMENT
    content = Column(Text, nullable=False)
    market_condition = Column(String(32), nullable=True)
    signal_quality = Column(String(16), nullable=True)
    risk_level = Column(String(16), nullable=True)
    continuation_prob = Column(Float, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)


class ReplayData(Base):
    __tablename__ = "replay_data"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, nullable=False)
    price = Column(Float, nullable=False)
    agg_buy_delta = Column(Float, default=0.0)
    agg_sell_delta = Column(Float, default=0.0)
    cvd = Column(Float, default=0.0)
    velocity = Column(Float, default=0.0)
    acceleration = Column(Float, default=0.0)
    imbalance = Column(Float, default=0.0)
    bid_volume = Column(Float, default=0.0)
    ask_volume = Column(Float, default=0.0)
    raw_snapshot = Column(JSON, default=dict)


class MarketSnapshot(Base):
    __tablename__ = "market_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    timestamp = Column(DateTime, default=datetime.utcnow)
    price = Column(Float, nullable=False)
    bid = Column(Float, nullable=True)
    ask = Column(Float, nullable=True)
    spread = Column(Float, nullable=True)
    agg_buy_delta_1s = Column(Float, default=0.0)
    agg_sell_delta_1s = Column(Float, default=0.0)
    cvd = Column(Float, default=0.0)
    velocity_1s = Column(Float, default=0.0)
    imbalance = Column(Float, default=0.0)


class Config(Base):
    __tablename__ = "configs"

    id = Column(Integer, primary_key=True, autoincrement=True)
    key = Column(String(64), unique=True, nullable=False)
    value = Column(Text, nullable=False)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class SignalQueue(Base):
    """
    Decoupled execution queue.
    Backend enqueues validated signals; local MT5 executor polls and ACKs.
    """
    __tablename__ = "signal_queue"

    id = Column(Integer, primary_key=True, autoincrement=True)
    signal_type = Column(String(32), nullable=False)
    side = Column(String(4), nullable=False)          # BUY / SELL
    confidence = Column(Float, nullable=False)
    price = Column(Float, nullable=False)
    quality_score = Column(Integer, nullable=True)
    regime = Column(String(20), nullable=True)
    adaptive_sl = Column(Float, nullable=True)
    adaptive_tp = Column(Float, nullable=True)
    payload = Column(JSON, nullable=False)             # full signal dict for executor
    status = Column(String(12), default="PENDING")     # PENDING/EXECUTED/FAILED/EXPIRED
    created_at = Column(DateTime, default=datetime.utcnow)
    expires_at = Column(DateTime, nullable=False)
    executed_at = Column(DateTime, nullable=True)
    mt5_ticket = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)


class PerformanceMetric(Base):
    __tablename__ = "performance_metrics"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String(32), nullable=False)
    win_rate = Column(Float, default=0.0)
    avg_pnl = Column(Float, default=0.0)
    avg_hold_seconds = Column(Float, default=0.0)
    total_trades = Column(Integer, default=0)
    winning_trades = Column(Integer, default=0)
    losing_trades = Column(Integer, default=0)
    total_pnl = Column(Float, default=0.0)
    fakeout_rate = Column(Float, default=0.0)
    continuation_success_rate = Column(Float, default=0.0)
    computed_at = Column(DateTime, default=datetime.utcnow)

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional


class Settings(BaseSettings):
    # Anthropic
    anthropic_api_key: str = Field(default="", env="ANTHROPIC_API_KEY")

    # Binance (public streams — no auth needed)
    binance_api_key: Optional[str] = Field(default=None, env="BINANCE_API_KEY")
    binance_api_secret: Optional[str] = Field(default=None, env="BINANCE_API_SECRET")

    # Server
    host: str = "0.0.0.0"
    port: int = Field(default=8000, env="PORT")
    debug: bool = True

    # Database
    database_url: str = "sqlite+aiosqlite:///./trading.db"

    # Binance stream — BTC
    symbol: str = "BTCUSDT"
    binance_ws_base: str = "wss://stream.binance.com:9443/stream"

    # Signal engine — tuned for BTC $100 TP / $30 SL (R:R 3.33:1)
    # Tight SL → need high directional conviction across all windows
    min_delta_threshold: float = 600000.0    # USD notional — strong flow only
    min_velocity_threshold: float = 200000.0 # USD/s — need real momentum
    min_confidence: float = 0.70            # higher bar — fewer but better signals
    min_imbalance_ratio: float = 0.68
    signal_cooldown_seconds: float = 10.0   # max one signal per 10s
    signal_type_cooldown_seconds: float = 20.0  # per-type: avoid repeat signals

    # Trade execution
    lot_size: float = 1.0                   # 1 BTC lot
    tp_usd_per_lot: float = 100.0           # $100 price move = TP
    sl_usd_per_lot: float = 30.0            # $30 price move = SL  → R:R = 3.33:1
    max_hold_seconds: int = 300             # 5min hard exit for BTC

    # MT5 / Exness — BTC
    mt5_login: Optional[int] = Field(default=None, env="MT5_LOGIN")
    mt5_password: Optional[str] = Field(default=None, env="MT5_PASSWORD")
    mt5_server: Optional[str] = Field(default=None, env="MT5_SERVER")
    mt5_terminal_path: Optional[str] = Field(default=None, env="MT5_TERMINAL_PATH")
    mt5_symbol: str = Field(default="BTCUSDm", env="MT5_SYMBOL")
    mt5_magic: int = 20250515
    mt5_deviation: int = 20
    mt5_poll_interval: float = 0.5

    # AI — feature toggles
    ai_signals_enabled: bool = True   # batch signal analysis + market background loop
    ai_weakness_enabled: bool = True  # trade weakness monitor

    # AI — rate limiting (prevents API spam during high volatility)
    max_ai_calls_per_minute: int = 15
    cooldown_between_same_direction_signals: float = 30.0  # seconds

    # Signal queue — decoupled execution for Railway → local MT5
    signal_queue_expiry_seconds: int = 60

    # Global kill switch — persisted in Config table, loaded on startup
    global_trading_enabled: bool = True

    # AI — batch mode (no per-signal validation)
    ai_model: str = "claude-sonnet-4-6"
    ai_analysis_interval: int = 30          # background market analysis every 30s
    ai_batch_size: int = 5                  # analyze after every N new signals
    ai_batch_interval: int = 60             # or every 60s if batch not full yet

    # Risk management
    min_quality_score: int = 68             # 0-100 — regime params override per-regime
    exec_health_min: str = "GOOD"           # EXCELLENT/GOOD/DEGRADED/UNSAFE
    blocked_sessions: list[str] = ["DEAD"]  # auto-trading blocked in these sessions
    cooldown_losses_medium: int = 2         # consecutive losses → 2min pause
    cooldown_losses_hard: int = 3           # consecutive losses → 5min pause
    cooldown_medium_seconds: int = 120
    cooldown_hard_seconds: int = 300

    # Rolling windows (seconds)
    windows: list[int] = [1, 3, 5, 10]

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


settings = Settings()

from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy import text
import structlog

from .models import Base
from config import settings

log = structlog.get_logger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    connect_args={"check_same_thread": False},
)

AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# New columns added to existing tables — ALTER TABLE ADD COLUMN for each.
# SQLite ignores "duplicate column" at the exception level; we catch and skip.
_MIGRATIONS = [
    # trades table
    "ALTER TABLE trades ADD COLUMN mt5_ticket INTEGER",
    "ALTER TABLE trades ADD COLUMN mt5_symbol VARCHAR(16)",
    "ALTER TABLE trades ADD COLUMN swap FLOAT DEFAULT 0.0",
    "ALTER TABLE trades ADD COLUMN signal_quality_score INTEGER",
    "ALTER TABLE trades ADD COLUMN signal_breakout_phase VARCHAR(16)",
    "ALTER TABLE trades ADD COLUMN regime VARCHAR(20)",
    "ALTER TABLE trades ADD COLUMN session VARCHAR(16)",
    "ALTER TABLE trades ADD COLUMN adaptive_sl FLOAT",
    "ALTER TABLE trades ADD COLUMN adaptive_tp FLOAT",
    # signals table
    "ALTER TABLE signals ADD COLUMN quality_score INTEGER",
    "ALTER TABLE signals ADD COLUMN breakout_phase VARCHAR(16)",
    "ALTER TABLE signals ADD COLUMN regime VARCHAR(20)",
    "ALTER TABLE signals ADD COLUMN session VARCHAR(16)",
    "ALTER TABLE signals ADD COLUMN ai_bias VARCHAR(8)",
    "ALTER TABLE signals ADD COLUMN executed BOOLEAN DEFAULT 0",
    "ALTER TABLE signals ADD COLUMN skipped BOOLEAN DEFAULT 0",
    "ALTER TABLE signals ADD COLUMN skip_reason TEXT",
]


async def init_db():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # Apply migrations for columns added after initial schema creation
        for stmt in _MIGRATIONS:
            try:
                await conn.execute(text(stmt))
            except Exception:
                pass  # column already exists — safe to ignore


async def get_session() -> AsyncSession:
    async with AsyncSessionLocal() as session:
        yield session

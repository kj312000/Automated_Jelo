"""
Persistent runtime config — survives Railway redeploys.

Uses the existing `configs` SQLite table (Config model).
Call load_and_apply() once at startup to restore last-saved state.
Call save() / save_bulk() after every runtime change.
"""
import json
from datetime import datetime, timezone

import structlog
from sqlalchemy import select

from database.db import AsyncSessionLocal
from database.models import Config as ConfigModel

log = structlog.get_logger(__name__)


async def load_and_apply(settings, ai_service=None) -> dict:
    """
    Read all rows from `configs` table, apply to settings / ai_service.
    Returns dict of {key: applied_value}.
    """
    applied: dict = {}
    try:
        async with AsyncSessionLocal() as session:
            rows = (await session.execute(select(ConfigModel))).scalars().all()

        for row in rows:
            try:
                value = json.loads(row.value)
            except (json.JSONDecodeError, TypeError):
                value = row.value  # plain string fallback

            if hasattr(settings, row.key):
                try:
                    current = getattr(settings, row.key)
                    coerced = type(current)(value)
                    object.__setattr__(settings, row.key, coerced)
                    applied[row.key] = coerced
                except Exception:
                    pass  # type coercion failed — skip

        # Sync runtime-only toggles on ai_service
        if ai_service:
            if "ai_signals_enabled" in applied:
                ai_service.signals_enabled = bool(applied["ai_signals_enabled"])
            if "ai_weakness_enabled" in applied:
                ai_service.weakness_enabled = bool(applied["ai_weakness_enabled"])

        if applied:
            log.info("config_store.loaded", count=len(applied))

    except Exception as exc:
        log.error("config_store.load_failed", error=str(exc))

    return applied


async def save(key: str, value) -> None:
    """Upsert one config key."""
    try:
        async with AsyncSessionLocal() as session:
            row = (await session.execute(
                select(ConfigModel).where(ConfigModel.key == key)
            )).scalar_one_or_none()
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if row:
                row.value = json.dumps(value)
                row.updated_at = now
            else:
                session.add(ConfigModel(
                    key=key,
                    value=json.dumps(value),
                    updated_at=now,
                ))
            await session.commit()
    except Exception as exc:
        log.error("config_store.save_failed", key=key, error=str(exc))


async def save_bulk(changes: dict) -> None:
    """Save multiple keys at once (one upsert per key)."""
    for key, value in changes.items():
        await save(key, value)

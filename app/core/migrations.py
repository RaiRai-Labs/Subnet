"""Lightweight schema bootstrap (no Alembic for the MVP).

``init_models`` creates any missing tables from the registered ORM metadata.
Adapted from the RaiRaiApp ``core/migrations.py`` pattern.
"""

from app.core.database import engine

# Import models package so all tables are registered on Base.metadata.
import app.models  # noqa: F401
from app.models import Base


async def init_models() -> None:
    """Create all tables that do not yet exist."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

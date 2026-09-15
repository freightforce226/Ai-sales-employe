"""
Purpose of this file.
Database session management.
Responsibility of this file.
Initializing the async SQLAlchemy engine and providing dependency injection for AsyncSession.
"""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.core.config import get_settings

settings = get_settings()

import logging
from sqlalchemy import event

logging.getLogger("sqlalchemy.engine").setLevel(logging.WARNING)
logger = logging.getLogger("app.db.session")

engine = create_async_engine(
    settings.database_url,
    echo=False,
    future=True,
    pool_pre_ping=True,
    pool_size=10,
    max_overflow=2,
    pool_timeout=30,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }
)

# Connection Telemetry Events
_checked_out_connections = 0

@event.listens_for(engine.sync_engine.pool, "checkout")
def _receive_checkout(dbapi_connection, connection_record, connection_proxy):
    global _checked_out_connections
    _checked_out_connections += 1
    logger.info(f"DB Connection Checked Out. Active connections: {_checked_out_connections}")

@event.listens_for(engine.sync_engine.pool, "checkin")
def _receive_checkin(dbapi_connection, connection_record):
    global _checked_out_connections
    _checked_out_connections = max(0, _checked_out_connections - 1)
    logger.info(f"DB Connection Released/Checked In. Active connections: {_checked_out_connections}")

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autoflush=False,
)

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """
    Dependency to yield an async database session.
    """
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise

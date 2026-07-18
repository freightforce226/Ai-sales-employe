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
logging.getLogger("sqlalchemy.engine").setLevel(
    logging.INFO if settings.log_level.upper() == "DEBUG" else logging.WARNING
)

engine = create_async_engine(
    settings.database_url,
    echo=(settings.log_level.upper() == "DEBUG"),
    future=True,
    pool_pre_ping=True,
    pool_size=20,
    max_overflow=10,
    connect_args={
        "statement_cache_size": 0,
        "prepared_statement_cache_size": 0,
    }
)

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

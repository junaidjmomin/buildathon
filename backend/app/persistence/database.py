from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from functools import lru_cache

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker

from app.core.config import get_settings


@lru_cache
def get_engine() -> Engine | None:
    settings = get_settings()
    if not settings.database_url:
        return None
    connect_args = {}
    if (
        settings.database_disable_prepared_statements
        and settings.database_url.startswith("postgresql+psycopg")
    ):
        # Safe for Supabase transaction-mode poolers; session/direct URLs may opt back in.
        connect_args["prepare_threshold"] = None
    return create_engine(
        settings.database_url,
        pool_pre_ping=True,
        pool_size=settings.database_pool_size,
        max_overflow=settings.database_max_overflow,
        pool_recycle=300,
        connect_args=connect_args,
    )


@lru_cache
def get_session_factory() -> sessionmaker[Session] | None:
    engine = get_engine()
    if engine is None:
        return None
    return sessionmaker(bind=engine, expire_on_commit=False)


@contextmanager
def session_scope() -> Iterator[Session]:
    factory = get_session_factory()
    if factory is None:
        raise RuntimeError("DATABASE_URL is not configured")
    with factory.begin() as session:
        yield session

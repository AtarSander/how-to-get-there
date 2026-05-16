from __future__ import annotations

from functools import lru_cache

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config.settings import settings


def resolve_database_url() -> str:
    database_url = settings.database_url or settings.database_private_url
    if not database_url:
        raise RuntimeError(
            "DATABASE_URL is not configured. Set it in the project .env file."
        )

    if database_url.startswith("postgres://"):
        database_url = database_url.replace(
            "postgres://",
            "postgresql+psycopg2://",
            1,
        )
    elif database_url.startswith("postgresql://"):
        database_url = database_url.replace(
            "postgresql://",
            "postgresql+psycopg2://",
            1,
        )

    return database_url


@lru_cache(maxsize=1)
def get_engine() -> Engine:
    return create_engine(
        resolve_database_url(),
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=2,
    )


def reset_engine_cache() -> None:
    get_engine.cache_clear()

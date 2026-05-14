import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine

from config.settings import settings


@st.cache_resource
def get_engine() -> Engine:
    database_url = settings.database_url or settings.database_private_url

    if not database_url:
        database_url = st.secrets["database"]["url"]

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

    return create_engine(
        database_url,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=2,
    )

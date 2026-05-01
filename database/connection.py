import streamlit as st
from sqlalchemy import create_engine
from sqlalchemy.engine import Engine


@st.cache_resource
def get_engine() -> Engine:
    database_url = st.secrets["database"]["url"]

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

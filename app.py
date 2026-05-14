import streamlit as st

from config.logging import configure_logging
from loguru import logger


def main():
    st.title("SPDB")
    logger.info("Starting SPDB app.")
    logger.success("SPDB app initialized.")


if __name__ == "__main__":
    configure_logging()
    main()

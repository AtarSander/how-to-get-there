from pathlib import Path
import sys

from sqlalchemy import text
from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.gtfs import GTFS_TABLES
from database.connection import get_engine


def main() -> None:
    engine = get_engine()

    with engine.begin() as conn:
        for table in GTFS_TABLES.values():
            logger.info("Dropping {}...", table)
            conn.execute(text(f'DROP TABLE IF EXISTS "{table}" CASCADE;'))

    logger.success("GTFS tables removed")


if __name__ == "__main__":
    main()

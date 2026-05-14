from pathlib import Path
import sys

from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.logging import configure_logging
from database.connection import get_engine
from scripts.download_gtfs import download_and_extract_gtfs
from scripts.import_gtfs import import_gtfs


def main() -> None:
    configure_logging()

    try:
        logger.info("Downloading GTFS.")
        download_and_extract_gtfs()

        logger.info("Importing GTFS into PostgreSQL.")
        engine = get_engine()
        import_gtfs(engine)

        logger.success("GTFS update completed successfully.")
    except Exception as exc:
        logger.error("GTFS update failed: {}", exc)
        raise


if __name__ == "__main__":
    main()

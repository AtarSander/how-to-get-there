from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.logging import configure_logging
from database.connection import get_engine
from scripts.download_osm_road_network import download_osm_road_network
from scripts.import_osm_road_network import import_osm_road_network


def main() -> None:
    configure_logging()

    try:
        logger.info("Downloading OSM road network.")
        download_osm_road_network()

        logger.info("Importing OSM road network into PostgreSQL.")
        engine = get_engine()
        import_osm_road_network(engine)

        logger.success("OSM road network update completed successfully.")
    except Exception as exc:
        logger.exception("OSM road network update failed: {}", exc)
        raise


if __name__ == "__main__":
    main()

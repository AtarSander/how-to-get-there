from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.logging import configure_logging
from database.connection import get_engine
from database.queries import replace_zdm_apr_profiles
from services.zdm_apr import fetch_zdm_apr_import_dataset


def import_zdm_apr_profiles() -> None:
    logger.info("Downloading ZDM APR hourly traffic profiles.")
    dataset = fetch_zdm_apr_import_dataset()
    logger.info(
        "Downloaded {} APR points and {} hourly direction records.",
        len(dataset.points),
        len(dataset.hourly_profiles),
    )

    replace_zdm_apr_profiles(
        engine=get_engine(),
        points=dataset.points,
        hourly_profiles=dataset.hourly_profiles,
    )
    logger.success("Imported ZDM APR hourly traffic profiles into the database.")


def main() -> None:
    configure_logging()
    try:
        import_zdm_apr_profiles()
    except Exception as exc:
        logger.exception("ZDM APR profile import failed: {}", exc)
        raise


if __name__ == "__main__":
    main()

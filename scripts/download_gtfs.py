from __future__ import annotations

import shutil
import sys
import zipfile
from pathlib import Path
from urllib.request import Request, urlopen

from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.gtfs import REQUIRED_GTFS_FILES
from config.logging import configure_logging
from config.settings import settings


def get_gtfs_zip_path():
    return settings.raw_data_path / "ztm_gtfs.zip"


def get_gtfs_tmp_path():
    return settings.raw_data_path / "gtfs_tmp"


def download_gtfs_zip() -> None:
    settings.raw_data_path.mkdir(parents=True, exist_ok=True)

    gtfs_zip_path = get_gtfs_zip_path()

    logger.info("Downloading GTFS archive from {}.", settings.gtfs_url)

    request = Request(
        settings.gtfs_url,
        headers={"User-Agent": settings.gtfs_download_user_agent},
    )

    with urlopen(request, timeout=settings.gtfs_download_timeout_seconds) as response:
        data = response.read()

    if not data:
        raise RuntimeError("Downloaded GTFS archive is empty.")

    gtfs_zip_path.write_bytes(data)

    logger.success("Saved GTFS archive to {}.", gtfs_zip_path)


def extract_gtfs_zip() -> None:
    gtfs_zip_path = get_gtfs_zip_path()
    gtfs_tmp_path = get_gtfs_tmp_path()

    if not gtfs_zip_path.exists():
        raise FileNotFoundError(f"Missing GTFS archive: {gtfs_zip_path}")

    if gtfs_tmp_path.exists():
        shutil.rmtree(gtfs_tmp_path)

    gtfs_tmp_path.mkdir(parents=True, exist_ok=True)

    try:
        with zipfile.ZipFile(gtfs_zip_path, "r") as zip_file:
            zip_file.extractall(gtfs_tmp_path)
    except zipfile.BadZipFile as exc:
        raise RuntimeError(
            f"Downloaded GTFS file is not a valid ZIP: {gtfs_zip_path}"
        ) from exc

    logger.success("Extracted GTFS archive to {}.", gtfs_tmp_path)


def validate_gtfs_files() -> None:
    gtfs_tmp_path = get_gtfs_tmp_path()

    existing_files = {path.name for path in gtfs_tmp_path.iterdir()}
    missing_files = REQUIRED_GTFS_FILES - existing_files

    if missing_files:
        raise RuntimeError(f"Missing required GTFS files: {sorted(missing_files)}")

    logger.success("Validated required GTFS files.")


def replace_current_gtfs() -> None:
    gtfs_tmp_path = get_gtfs_tmp_path()

    if settings.gtfs_path.exists():
        shutil.rmtree(settings.gtfs_path)

    settings.gtfs_path.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(gtfs_tmp_path), str(settings.gtfs_path))

    logger.success("Replaced current GTFS dataset at {}.", settings.gtfs_path)


def download_and_extract_gtfs() -> None:
    download_gtfs_zip()
    extract_gtfs_zip()
    validate_gtfs_files()
    replace_current_gtfs()


def main() -> None:
    configure_logging()

    try:
        download_and_extract_gtfs()
        logger.success("GTFS downloaded and extracted to {}.", settings.gtfs_path)
    except Exception as exc:
        logger.exception("GTFS download failed: {}", exc)
        raise


if __name__ == "__main__":
    main()

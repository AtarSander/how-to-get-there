from pathlib import Path
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    database_url: str
    ztm_api_url: str | None = None

    gtfs_url: str = "https://gtfs.ztm.waw.pl/last"
    database_url: str | None = None

    raw_data_path: Path = BASE_DIR / "data" / "raw"
    gtfs_path: Path = BASE_DIR / "data" / "gtfs"
    processed_data_path: Path = BASE_DIR / "data" / "processed"

    class Config:
        env_file = ".env"


settings = Settings()

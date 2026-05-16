from pathlib import Path
from datetime import date

from pydantic_settings import SettingsConfigDict
from pydantic_settings import BaseSettings

BASE_DIR = Path(__file__).resolve().parents[1]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env")

    database_url: str | None = None
    database_private_url: str | None = None
    ztm_api_url: str | None = None

    gtfs_url: str = "https://gtfs.ztm.waw.pl/last"
    gtfs_download_timeout_seconds: int = 60
    gtfs_download_user_agent: str = "Mozilla/5.0"
    gtfs_import_start_date: date | None = None
    gtfs_import_days: int = 1
    gtfs_create_heavy_indexes: bool = False
    gtfs_create_optional_indexes: bool = False
    gtfs_keep_stop_times: bool = False
    gtfs_include_pseudo_metro: bool = True
    gtfs_stop_times_read_chunksize: int = 50_000
    gtfs_shapes_read_chunksize: int = 100_000
    gtfs_sql_insert_chunksize: int = 2_000
    gtfs_small_table_sql_chunksize: int = 5_000

    osm_place_name: str = "Warsaw, Masovian Voivodeship, Poland"
    osm_network_type: str = "drive"
    osm_use_postgis: bool = True
    osm_sql_insert_chunksize: int = 10_000

    earth_radius_m: int = 6_371_000
    car_default_speed_kmh: float = 40.0
    car_use_database_edges: bool = True
    car_road_edges_limit: int | None = None
    car_traffic_profile_enabled: bool = True
    car_traffic_profile_min_multiplier: float = 1.0
    car_traffic_profile_max_multiplier: float = 2.5
    car_traffic_center_lat: float = 52.2297
    car_traffic_center_lon: float = 21.0122

    zdm_apr_feature_layer_url: str = (
        "https://services7.arcgis.com/gpQ1tnydOYYnGpcS/arcgis/rest/services/"
        "APR_ZDM_MAPA_DASHBOARD_2023/FeatureServer/0"
    )
    zdm_apr_source_year: int = 2023
    zdm_apr_download_timeout_seconds: int = 60
    zdm_apr_download_page_size: int = 2_000

    public_transport_walking_speed_mps: float = 1.4
    public_transport_max_stop_distance_m: int = 1_000
    public_transport_stop_limit: int = 25
    public_transport_max_transfers: int = 2
    public_transport_search_window_hours: int = 4
    public_transport_segment_limit: int = 50_000
    public_transport_transfer_buffer_seconds: int = 120
    public_transport_result_limit: int = 3

    park_and_ride_candidate_limit: int = 5
    park_and_ride_result_limit: int = 3
    park_and_ride_min_transfer_seconds: int = 120

    raw_data_path: Path = BASE_DIR / "data" / "raw"
    config_data_path: Path = BASE_DIR / "data" / "config"
    gtfs_path: Path = BASE_DIR / "data" / "gtfs"
    osm_road_graph_path: Path = BASE_DIR / "data" / "raw" / "warsaw_drive.graphml"
    osmnx_cache_path: Path = BASE_DIR / "data" / "raw" / "osmnx_cache"
    processed_data_path: Path = BASE_DIR / "data" / "processed"

    flask_host: str = "127.0.0.1"
    flask_port: int = 5000
    flask_debug: bool = True
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    geocoding_user_agent: str = "how-to-get-there/0.1 (Warsaw route planner)"
    geocoding_contact_email: str | None = None
    geocoding_timeout_seconds: int = 10

    @property
    def cors_origins_list(self) -> list[str]:
        return [
            origin.strip() for origin in self.cors_origins.split(",") if origin.strip()
        ]


settings = Settings()

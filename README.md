# How to get there

Spatial routing prototype for Warsaw. The project compares travel options by car,
public transport, and Park & Ride using GTFS-like transit data, OpenStreetMap
road data, and PostGIS.

## Structure

```text
app.py                  Streamlit entry point
config/                 Runtime settings, schema constants, JSON loaders
data/config/            Static domain data: metro model, Park & Ride locations
database/               SQLAlchemy connection and query helpers
scripts/                Data download/import/update scripts
services/               Routing and route comparison logic
tests/                  Pytest test suite
```

Large downloaded datasets live under `data/raw/` and `data/gtfs/` locally and
should not be committed.

## Requirements

- Python 3.14+
- `uv`
- PostgreSQL with PostGIS enabled

Enable PostGIS in the target database:

```sql
CREATE EXTENSION IF NOT EXISTS postgis;
SELECT postgis_version();
```

## Configuration

Create `.env` in the project root:

```env
DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB_NAME

GTFS_IMPORT_DAYS=1
GTFS_KEEP_STOP_TIMES=false
GTFS_CREATE_HEAVY_INDEXES=false
GTFS_CREATE_OPTIONAL_INDEXES=false
GTFS_INCLUDE_PSEUDO_METRO=true
```

The pseudo-metro model is stored in `data/config/metro.json`. Park & Ride
locations are stored in `data/config/park_and_ride.json`.

## Commands

Install dependencies:

```bash
uv sync
```

Run tests:

```bash
uv run pytest
```

Download and import Warsaw GTFS:

```bash
uv run python scripts/update_gtfs.py
```

Download and import Warsaw OSM road network:

```bash
uv run python scripts/update_osm_road_network.py
```

Run only download/import steps if needed:

```bash
uv run python scripts/download_gtfs.py
uv run python scripts/import_gtfs.py
uv run python scripts/download_osm_road_network.py
uv run python scripts/import_osm_road_network.py
```

Run the Streamlit app:

```bash
uv run streamlit run app.py
```

## Notes

- GTFS from ZTM does not include Warsaw Metro, so the project generates a
  lightweight pseudo-GTFS metro model from `data/config/metro.json`.
- Car routing uses imported OSM road edges. If road data is unavailable,
  route comparison falls back to a straight-line estimate.

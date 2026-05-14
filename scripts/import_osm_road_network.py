from __future__ import annotations

import ast
import math
import re
import sys
from pathlib import Path
from typing import Any

import pandas as pd
from loguru import logger
from sqlalchemy import Boolean, Float, Integer, Text, text
from sqlalchemy.engine import Engine

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.osm import (
    OSM_NON_NUMERIC_MAXSPEED_VALUES,
    OSM_TRUE_VALUES,
    ROAD_EDGES_STAGE_TABLE,
    ROAD_EDGES_TABLE,
    ROAD_NODES_STAGE_TABLE,
    ROAD_NODES_TABLE,
)
from config.logging import configure_logging
from config.settings import settings
from database.connection import get_engine


def get_osm_road_graph_path() -> Path:
    return settings.osm_road_graph_path


def normalize_osm_value(value: Any) -> str | None:
    if value is None:
        return None

    if isinstance(value, float) and math.isnan(value):
        return None

    if isinstance(value, list | tuple | set):
        return ";".join(str(item) for item in value if item is not None)

    return str(value)


def parse_osm_list(value: Any) -> list[Any]:
    if isinstance(value, list):
        return value

    if not isinstance(value, str):
        return [value]

    stripped_value = value.strip()

    if not stripped_value.startswith("["):
        return [value]

    try:
        parsed = ast.literal_eval(stripped_value)
    except (SyntaxError, ValueError):
        return [value]

    if isinstance(parsed, list):
        return parsed

    return [parsed]


def parse_maxspeed_kmh(value: Any) -> float | None:
    if value is None:
        return None

    speeds: list[float] = []

    for item in parse_osm_list(value):
        if item is None:
            continue

        item_text = str(item).lower().strip()
        if item_text in OSM_NON_NUMERIC_MAXSPEED_VALUES:
            continue

        match = re.search(r"\d+(?:\.\d+)?", item_text)
        if match is None:
            continue

        speed = float(match.group(0))
        if "mph" in item_text:
            speed *= 1.609344

        speeds.append(speed)

    if not speeds:
        return None

    return max(speeds)


def is_oneway(value: Any) -> bool:
    if isinstance(value, bool):
        return value

    if value is None:
        return False

    return str(value).lower() in OSM_TRUE_VALUES


def drop_osm_road_tables(engine: Engine) -> None:
    logger.info("Dropping existing OSM road tables.")

    with engine.begin() as conn:
        conn.execute(text(f'DROP TABLE IF EXISTS "{ROAD_EDGES_TABLE}" CASCADE;'))
        conn.execute(text(f'DROP TABLE IF EXISTS "{ROAD_NODES_TABLE}" CASCADE;'))
        conn.execute(text(f'DROP TABLE IF EXISTS "{ROAD_EDGES_STAGE_TABLE}" CASCADE;'))
        conn.execute(text(f'DROP TABLE IF EXISTS "{ROAD_NODES_STAGE_TABLE}" CASCADE;'))

    logger.success("Dropped existing OSM road tables.")


def graph_to_dataframes(graph) -> tuple[pd.DataFrame, pd.DataFrame]:
    import osmnx as ox

    nodes_gdf, edges_gdf = ox.graph_to_gdfs(graph, nodes=True, edges=True)

    nodes_df = pd.DataFrame(
        {
            "node_id": [str(node_id) for node_id in nodes_gdf.index],
            "osmid": [str(node_id) for node_id in nodes_gdf.index],
            "lat": nodes_gdf["y"].astype(float).values,
            "lon": nodes_gdf["x"].astype(float).values,
            "street_count": nodes_gdf.get("street_count", pd.Series(index=nodes_gdf.index))
            .fillna(0)
            .astype(int)
            .values,
        }
    )

    edge_rows: list[dict[str, Any]] = []
    node_points = {
        row.node_id: (row.lat, row.lon)
        for row in nodes_df[["node_id", "lat", "lon"]].itertuples(index=False)
    }

    for (source, target, key), row in edges_gdf.iterrows():
        source_lat, source_lon = node_points[str(source)]
        target_lat, target_lon = node_points[str(target)]

        edge_rows.append(
            {
                "edge_id": f"{source}-{target}-{key}",
                "source": str(source),
                "target": str(target),
                "key": int(key),
                "source_lat": source_lat,
                "source_lon": source_lon,
                "target_lat": target_lat,
                "target_lon": target_lon,
                "osmid": normalize_osm_value(row.get("osmid")),
                "name": normalize_osm_value(row.get("name")),
                "highway": normalize_osm_value(row.get("highway")),
                "oneway": is_oneway(row.get("oneway")),
                "reversed": is_oneway(row.get("reversed")),
                "length_m": float(row.get("length", 0.0) or 0.0),
                "max_speed_kmh": parse_maxspeed_kmh(row.get("maxspeed")),
                "lanes": normalize_osm_value(row.get("lanes")),
                "bridge": normalize_osm_value(row.get("bridge")),
                "tunnel": normalize_osm_value(row.get("tunnel")),
                "access": normalize_osm_value(row.get("access")),
            }
        )

    edges_df = pd.DataFrame(edge_rows)

    return nodes_df, edges_df


def load_graph(path: Path):
    import osmnx as ox

    if not path.exists():
        raise FileNotFoundError(f"Missing OSM road graph: {path}")

    logger.info("Loading OSM road graph from {}.", path)
    graph = ox.load_graphml(path)

    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise RuntimeError(f"OSM road graph is empty: {path}")

    return graph


def load_base_tables(
    engine: Engine,
    nodes_df: pd.DataFrame,
    edges_df: pd.DataFrame,
) -> None:
    logger.info("Loading OSM road base tables.")

    nodes_df.to_sql(
        ROAD_NODES_TABLE,
        engine,
        if_exists="replace",
        index=False,
        chunksize=settings.osm_sql_insert_chunksize,
        dtype={
            "node_id": Text(),
            "osmid": Text(),
            "lat": Float(),
            "lon": Float(),
            "street_count": Integer(),
        },
    )
    edges_df.to_sql(
        ROAD_EDGES_TABLE,
        engine,
        if_exists="replace",
        index=False,
        chunksize=settings.osm_sql_insert_chunksize,
        dtype={
            "edge_id": Text(),
            "source": Text(),
            "target": Text(),
            "key": Integer(),
            "source_lat": Float(),
            "source_lon": Float(),
            "target_lat": Float(),
            "target_lon": Float(),
            "osmid": Text(),
            "name": Text(),
            "highway": Text(),
            "oneway": Boolean(),
            "reversed": Boolean(),
            "length_m": Float(),
            "max_speed_kmh": Float(),
            "lanes": Text(),
            "bridge": Text(),
            "tunnel": Text(),
            "access": Text(),
        },
    )

    logger.success(
        "Loaded {} road nodes and {} road edges into base tables.",
        len(nodes_df),
        len(edges_df),
    )


def is_postgis_available(engine: Engine) -> bool:
    with engine.begin() as conn:
        result = conn.execute(text("""
            SELECT installed_version IS NOT NULL AS installed,
                   default_version IS NOT NULL AS available
            FROM pg_available_extensions
            WHERE name = 'postgis';
        """)).mappings().first()

    return bool(result and (result["installed"] or result["available"]))


def add_postgis_geometry(engine: Engine) -> None:
    logger.info("Adding PostGIS geometry to OSM road tables.")

    with engine.begin() as conn:
        conn.execute(text("CREATE EXTENSION IF NOT EXISTS postgis;"))

        conn.execute(text(f"""
            ALTER TABLE {ROAD_NODES_TABLE}
            ADD COLUMN IF NOT EXISTS geom geometry(Point, 4326);
        """))

        conn.execute(text(f"""
            UPDATE {ROAD_NODES_TABLE}
            SET geom = ST_SetSRID(ST_MakePoint(lon, lat), 4326)
            WHERE lon IS NOT NULL
              AND lat IS NOT NULL;
        """))

        conn.execute(text(f"""
            ALTER TABLE {ROAD_EDGES_TABLE}
            ADD COLUMN IF NOT EXISTS geom geometry(LineString, 4326);
        """))

        conn.execute(text(f"""
            UPDATE {ROAD_EDGES_TABLE}
            SET geom = ST_SetSRID(
                ST_MakeLine(
                    ST_MakePoint(source_lon, source_lat),
                    ST_MakePoint(target_lon, target_lat)
                ),
                4326
            )
            WHERE source_lon IS NOT NULL
              AND source_lat IS NOT NULL
              AND target_lon IS NOT NULL
              AND target_lat IS NOT NULL;
        """))

        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{ROAD_NODES_TABLE}_geom
            ON {ROAD_NODES_TABLE}
            USING GIST (geom);
        """))

        conn.execute(text(f"""
            CREATE INDEX IF NOT EXISTS idx_{ROAD_EDGES_TABLE}_geom
            ON {ROAD_EDGES_TABLE}
            USING GIST (geom);
        """))

    logger.success("Added PostGIS geometry to OSM road tables.")


def create_indexes(engine: Engine) -> None:
    logger.info("Creating OSM road indexes.")

    statements = [
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_{ROAD_NODES_TABLE}_node_id
        ON {ROAD_NODES_TABLE}(node_id);
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_{ROAD_NODES_TABLE}_lat_lon
        ON {ROAD_NODES_TABLE}(lat, lon);
        """,
        f"""
        CREATE UNIQUE INDEX IF NOT EXISTS idx_{ROAD_EDGES_TABLE}_edge_id
        ON {ROAD_EDGES_TABLE}(edge_id);
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_{ROAD_EDGES_TABLE}_source
        ON {ROAD_EDGES_TABLE}(source);
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_{ROAD_EDGES_TABLE}_target
        ON {ROAD_EDGES_TABLE}(target);
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_{ROAD_EDGES_TABLE}_highway
        ON {ROAD_EDGES_TABLE}(highway);
        """,
        f"""
        CREATE INDEX IF NOT EXISTS idx_{ROAD_EDGES_TABLE}_source_target
        ON {ROAD_EDGES_TABLE}(source, target);
        """,
    ]

    with engine.begin() as conn:
        for statement in statements:
            conn.execute(text(statement))

    logger.success("Created OSM road indexes.")


def import_osm_road_network(engine: Engine) -> None:
    graph = load_graph(get_osm_road_graph_path())
    nodes_df, edges_df = graph_to_dataframes(graph)

    if nodes_df.empty or edges_df.empty:
        raise RuntimeError("OSM road graph conversion produced empty tables.")

    drop_osm_road_tables(engine)
    load_base_tables(engine, nodes_df, edges_df)
    create_indexes(engine)

    if settings.osm_use_postgis and is_postgis_available(engine):
        add_postgis_geometry(engine)
    elif settings.osm_use_postgis:
        logger.warning(
            "PostGIS extension is not available in this database. "
            "Imported OSM road network without geometry columns."
        )


def main() -> None:
    configure_logging()

    try:
        engine = get_engine()
        import_osm_road_network(engine)
        logger.success("OSM road network imported successfully.")
    except Exception as exc:
        logger.exception("OSM road network import failed: {}", exc)
        raise


if __name__ == "__main__":
    main()

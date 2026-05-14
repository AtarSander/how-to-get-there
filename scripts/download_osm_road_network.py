from __future__ import annotations

from pathlib import Path
import sys

from loguru import logger

sys.path.append(str(Path(__file__).resolve().parents[1]))

from config.logging import configure_logging
from config.settings import settings


def get_osm_road_graph_path() -> Path:
    return settings.osm_road_graph_path


def download_osm_road_network() -> None:
    import osmnx as ox

    graph_path = get_osm_road_graph_path()
    graph_path.parent.mkdir(parents=True, exist_ok=True)

    cache_path = settings.osmnx_cache_path
    cache_path.mkdir(parents=True, exist_ok=True)

    ox.settings.use_cache = True
    ox.settings.cache_folder = str(cache_path)
    ox.settings.log_console = False

    logger.info(
        "Downloading OSM road network for {} with network_type={}.",
        settings.osm_place_name,
        settings.osm_network_type,
    )

    graph = ox.graph_from_place(
        settings.osm_place_name,
        network_type=settings.osm_network_type,
        simplify=True,
        retain_all=False,
        truncate_by_edge=True,
    )

    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise RuntimeError("Downloaded OSM road graph is empty.")

    ox.save_graphml(graph, graph_path)

    logger.success(
        "Saved OSM road graph to {} ({} nodes, {} edges).",
        graph_path,
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )


def validate_osm_road_graph() -> None:
    import osmnx as ox

    graph_path = get_osm_road_graph_path()

    if not graph_path.exists():
        raise FileNotFoundError(f"Missing OSM road graph: {graph_path}")

    graph = ox.load_graphml(graph_path)

    if graph.number_of_nodes() == 0 or graph.number_of_edges() == 0:
        raise RuntimeError(f"OSM road graph is empty: {graph_path}")

    logger.success(
        "Validated OSM road graph at {} ({} nodes, {} edges).",
        graph_path,
        graph.number_of_nodes(),
        graph.number_of_edges(),
    )


def main() -> None:
    configure_logging()

    try:
        download_osm_road_network()
        validate_osm_road_graph()
        logger.success("OSM road network downloaded successfully.")
    except Exception as exc:
        logger.exception("OSM road network download failed: {}", exc)
        raise


if __name__ == "__main__":
    main()

from __future__ import annotations

from scripts.import_osm_road_network import (
    edge_geometry_positions,
    linestring_wkt_from_positions,
)


class FakeGeometry:
    def __init__(self, coords):
        self.coords = coords


def test_edge_geometry_positions_preserves_osm_curve_points() -> None:
    positions = edge_geometry_positions(
        FakeGeometry(
            [
                (21.0, 52.0),
                (21.01, 52.001),
                (21.02, 52.0),
            ]
        ),
        source_lat=52.0,
        source_lon=21.0,
        target_lat=52.0,
        target_lon=21.02,
    )

    assert positions == [
        (52.0, 21.0),
        (52.001, 21.01),
        (52.0, 21.02),
    ]
    assert linestring_wkt_from_positions(positions) == (
        "LINESTRING(21.0 52.0, 21.01 52.001, 21.02 52.0)"
    )


def test_edge_geometry_positions_falls_back_to_edge_endpoints() -> None:
    assert edge_geometry_positions(
        None,
        source_lat=52.0,
        source_lon=21.0,
        target_lat=52.01,
        target_lon=21.01,
    ) == [(52.0, 21.0), (52.01, 21.01)]

from __future__ import annotations

from services.gtfs_geometry import slice_polyline_by_shape_distance


def test_slice_polyline_by_shape_distance_returns_middle_section() -> None:
    points = (
        (52.0, 21.0),
        (52.001, 21.0),
        (52.002, 21.0),
        (52.003, 21.0),
    )

    sliced = slice_polyline_by_shape_distance(points, dist_from=80.0, dist_to=200.0)

    assert len(sliced) >= 2
    assert sliced[0] == points[0] or sliced[0] == points[1]
    assert sliced[-1] in points


def test_slice_polyline_by_shape_distance_returns_full_line_for_full_range() -> None:
    points = (
        (52.0, 21.0),
        (52.01, 21.0),
    )

    sliced = slice_polyline_by_shape_distance(points, dist_from=0.0, dist_to=10_000.0)

    assert sliced == points

from __future__ import annotations

import math
from typing import Any

try:  # Shapely is the production geometry engine for GIS review.
    from shapely.geometry import LineString, mapping, shape
    from shapely.geometry.base import BaseGeometry

    SHAPELY_AVAILABLE = True
except Exception:  # pragma: no cover - fallback for partially prepared envs
    LineString = None  # type: ignore[assignment]
    BaseGeometry = object  # type: ignore[assignment]
    mapping = None  # type: ignore[assignment]
    shape = None  # type: ignore[assignment]
    SHAPELY_AVAILABLE = False

Point = tuple[float, float]


def to_shape(geometry: dict[str, Any] | None) -> BaseGeometry | None:
    if not SHAPELY_AVAILABLE or not geometry:
        return None
    try:
        geom = shape(geometry)
    except Exception:
        return None
    if geom.is_empty:
        return None
    return geom


def geometry_relation(a: dict[str, Any] | None, b: dict[str, Any] | None) -> dict[str, bool]:
    ga = to_shape(a)
    gb = to_shape(b)
    if ga is None or gb is None:
        return {"intersects": False, "contains": False, "within": False, "crosses": False, "touches": False}
    return {
        "intersects": bool(ga.intersects(gb)),
        "contains": bool(ga.contains(gb)),
        "within": bool(ga.within(gb)),
        "crosses": bool(ga.crosses(gb)),
        "touches": bool(ga.touches(gb)),
    }


def geometry_distance(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float | None:
    ga = to_shape(a)
    gb = to_shape(b)
    if ga is not None and gb is not None:
        return float(ga.distance(gb))
    return _fallback_geometry_distance(a, b)


def risk_geometry(a: dict[str, Any] | None, b: dict[str, Any] | None = None) -> dict[str, Any] | None:
    ga = to_shape(a)
    gb = to_shape(b)
    if ga is not None and gb is not None and LineString and mapping:
        line = LineString([ga.representative_point(), gb.representative_point()])
        return dict(mapping(line))
    if ga is not None and mapping:
        return dict(mapping(ga.representative_point()))
    return _fallback_risk_geometry(a, b)


def geometry_points(geometry: dict[str, Any] | None) -> list[Point]:
    if not geometry:
        return []
    gtype = geometry.get("type")
    coords = geometry.get("coordinates")
    if not coords:
        return []
    if gtype == "Point":
        return [(float(coords[0]), float(coords[1]))]
    if gtype == "LineString":
        return [(float(x), float(y)) for x, y, *_ in coords]
    if gtype == "Polygon":
        ring = coords[0] if coords else []
        return [(float(x), float(y)) for x, y, *_ in ring]
    if gtype == "MultiLineString":
        return [(float(x), float(y)) for line in coords for x, y, *_ in line]
    if gtype == "MultiPolygon":
        return [(float(x), float(y)) for poly in coords for ring in poly[:1] for x, y, *_ in ring]
    return []


def centroid(geometry: dict[str, Any] | None) -> Point | None:
    points = geometry_points(geometry)
    if not points:
        return None
    return (sum(p[0] for p in points) / len(points), sum(p[1] for p in points) / len(points))


def distance(a: Point, b: Point) -> float:
    return math.hypot(a[0] - b[0], a[1] - b[1])


def point_to_segment_distance(point: Point, start: Point, end: Point) -> float:
    px, py = point
    x1, y1 = start
    x2, y2 = end
    dx = x2 - x1
    dy = y2 - y1
    if dx == 0 and dy == 0:
        return distance(point, start)
    t = max(0.0, min(1.0, ((px - x1) * dx + (py - y1) * dy) / (dx * dx + dy * dy)))
    projection = (x1 + t * dx, y1 + t * dy)
    return distance(point, projection)


def segment_distance(a1: Point, a2: Point, b1: Point, b2: Point) -> float:
    if segments_intersect(a1, a2, b1, b2):
        return 0.0
    return min(
        point_to_segment_distance(a1, b1, b2),
        point_to_segment_distance(a2, b1, b2),
        point_to_segment_distance(b1, a1, a2),
        point_to_segment_distance(b2, a1, a2),
    )


def segments_intersect(a: Point, b: Point, c: Point, d: Point) -> bool:
    def orient(p: Point, q: Point, r: Point) -> float:
        return (q[1] - p[1]) * (r[0] - q[0]) - (q[0] - p[0]) * (r[1] - q[1])

    def on_segment(p: Point, q: Point, r: Point) -> bool:
        return min(p[0], r[0]) <= q[0] <= max(p[0], r[0]) and min(p[1], r[1]) <= q[1] <= max(p[1], r[1])

    o1 = orient(a, b, c)
    o2 = orient(a, b, d)
    o3 = orient(c, d, a)
    o4 = orient(c, d, b)
    if o1 * o2 < 0 and o3 * o4 < 0:
        return True
    eps = 1e-9
    return (
        abs(o1) < eps
        and on_segment(a, c, b)
        or abs(o2) < eps
        and on_segment(a, d, b)
        or abs(o3) < eps
        and on_segment(c, a, d)
        or abs(o4) < eps
        and on_segment(c, b, d)
    )


def _fallback_geometry_distance(a: dict[str, Any] | None, b: dict[str, Any] | None) -> float | None:
    points_a = geometry_points(a)
    points_b = geometry_points(b)
    if not points_a or not points_b:
        return None
    if len(points_a) == 1 and len(points_b) == 1:
        return distance(points_a[0], points_b[0])
    segments_a = list(zip(points_a, points_a[1:])) or [(points_a[0], points_a[0])]
    segments_b = list(zip(points_b, points_b[1:])) or [(points_b[0], points_b[0])]
    return min(segment_distance(a1, a2, b1, b2) for a1, a2 in segments_a for b1, b2 in segments_b)


def _fallback_risk_geometry(a: dict[str, Any] | None, b: dict[str, Any] | None = None) -> dict[str, Any] | None:
    ca = centroid(a)
    cb = centroid(b) if b else None
    if ca and cb:
        return {"type": "LineString", "coordinates": [[ca[0], ca[1]], [cb[0], cb[1]]]}
    if ca:
        return {"type": "Point", "coordinates": [ca[0], ca[1]]}
    return a or b

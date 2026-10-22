"""Aggregate source geometries without deriving positions or dissolving areas."""

import json
import math

import geojson


def group_spatial(spatial: str, sensor_group: bool = False) -> str:
    """Validate and aggregate locations, preserving their original coordinates."""
    if not spatial:
        return ""
    parts = {}

    def finite(value):
        if isinstance(value, list):
            return all(finite(item) for item in value)
        return (
            not isinstance(value, bool)
            and isinstance(value, (int, float))
            and math.isfinite(value)
        )

    def collect(item):
        if not isinstance(item, dict):
            raise ValueError("Location must contain a GeoJSON geometry")
        kind = item.get("type")
        if kind == "Feature":
            collect(item.get("geometry"))
            return
        if kind in {"FeatureCollection", "GeometryCollection"}:
            children = item.get(
                "features" if kind == "FeatureCollection" else "geometries"
            )
            if not isinstance(children, list):
                raise ValueError("Invalid GeoJSON collection")
            for child in children:
                collect(child)
            return
        simple = {
            "MultiPoint": "Point",
            "MultiLineString": "LineString",
            "MultiPolygon": "Polygon",
        }
        if kind not in {"Point", "LineString", "Polygon", *simple}:
            raise ValueError(f"Unsupported location geometry: {kind}")
        coordinates = item.get("coordinates")
        if not isinstance(coordinates, list) or not finite(coordinates):
            raise ValueError(f"Invalid coordinates for {kind}")
        geometry = {"type": kind, "coordinates": coordinates}
        try:
            valid = geojson.loads(json.dumps(geometry)).is_valid
        except (TypeError, ValueError, IndexError, AttributeError):
            valid = False
        if not valid:
            raise ValueError(f"Invalid GeoJSON {kind} coordinates")
        if kind in simple:
            for coordinate in coordinates:
                collect({"type": simple[kind], "coordinates": coordinate})
            return
        if sensor_group and kind != "Point":
            raise ValueError(
                f"SDDI sensor groups require point locations; found {kind}"
            )
        # Retain original coordinates and holes, not geojson's rounded copy.
        parts[json.dumps(geometry, sort_keys=True, separators=(",", ":"))] = geometry

    collect(json.loads(spatial))
    geometries = [parts[key] for key in sorted(parts)]
    if not geometries:
        return ""
    types = {item["type"] for item in geometries}
    if len(types) == 1:
        result = {
            "type": "Multi" + geometries[0]["type"],
            "coordinates": [item["coordinates"] for item in geometries],
        }
    else:
        result = {"type": "GeometryCollection", "geometries": geometries}
    return json.dumps(result, allow_nan=False)

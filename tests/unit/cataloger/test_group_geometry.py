import json
from unittest.mock import patch

import pytest

from wrench.cataloger.sddi import SDDICataloger
from wrench.cataloger.sddi.spatial import group_spatial

RING = [[0, 0], [4, 0], [4, 4], [0, 0]]
HOLE = [[1, 1], [2, 1], [2, 2], [1, 1]]


def test_polygons_holes_precision_and_deduplication():
    ring = [[0.123456789, 0], [4, 0], [4, 4], [0.123456789, 0]]
    polygon = {"type": "Polygon", "coordinates": [ring, HOLE]}
    source = {
        "type": "FeatureCollection",
        "features": [polygon, {"type": "Feature", "geometry": polygon}],
    }
    result = json.loads(group_spatial(json.dumps(source)))
    assert result == {"type": "MultiPolygon", "coordinates": [[ring, HOLE]]}


def test_multipart_mixed_and_order_independence():
    polygons = {"type": "MultiPolygon", "coordinates": [[RING], [RING, HOLE]]}
    point = {"type": "MultiPoint", "coordinates": [[11, 48], [11, 48]]}
    source = {"type": "GeometryCollection", "geometries": [polygons, point]}
    result = group_spatial(json.dumps(source))
    source["geometries"].reverse()
    assert result == group_spatial(json.dumps(source))
    assert len(json.loads(result)["geometries"]) == 3


@pytest.mark.parametrize(
    "geometry",
    [
        {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1]]]},
        {"type": "Point", "coordinates": [float("nan"), 1]},
        {"type": "Feature", "geometry": None},
    ],
)
def test_invalid_geometry_rejected(geometry):
    with pytest.raises(ValueError):
        group_spatial(json.dumps(geometry))


def test_sensor_constraint_and_empty():
    assert group_spatial("") == ""
    assert group_spatial('{"type":"FeatureCollection","features":[]}') == ""
    with pytest.raises(ValueError, match="sensor groups"):
        group_spatial(json.dumps({"type": "Polygon", "coordinates": [RING]}), True)


def test_preflight_before_any_catalog_write(make_common_metadata):
    with patch("wrench.cataloger.sddi.cataloger.RemoteCKAN") as remote:
        cataloger = SDDICataloger("https://ckan", "key")
        group = make_common_metadata(spatial_extent='{"type":"Invalid"}')
        with pytest.raises(ValueError):
            cataloger.register(make_common_metadata(), [group])
        remote.return_value.call_action.assert_not_called()

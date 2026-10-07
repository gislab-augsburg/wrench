import json
from unittest.mock import patch

from wrench.cataloger.sddi import SDDICataloger


def test_typed_schema_payloads(make_common_metadata):
    with patch("wrench.cataloger.sddi.cataloger.RemoteCKAN"):
        cat = SDDICataloger("https://ckan", "key", "my-org")
    service = cat._create_online_service(make_common_metadata()).model_dump()
    assert service["type"] == "online-service"
    assert service["owner_org"] == "my-org"
    assert service["status"] == "draft"
    assert service["access_rights"] == "private" and service["private"]
    assert service["tags"] and not service["groups"]
    assert service["license_id"] == "notspecified"
    meta = make_common_metadata(
        is_sensor_group=True,
        observed_property="Temperature",
        spatial_extent=json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "geometry": {"type": "Point", "coordinates": [11, 48]},
                        "properties": {},
                    }
                ],
            }
        ),
    )
    device = cat._create_device_groups([meta])[0].model_dump()
    assert device["type"] == "device" and device["is_sensor_group"] == "true"
    assert device["service_standard"] == "OGC_SensorThings"
    assert device["observed_property"] == "Temperature"
    assert json.loads(device["spatial"])["type"] == "MultiPoint"
    assert device["tags"] and not device["groups"]

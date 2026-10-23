import json
from pathlib import Path
from unittest.mock import patch

import pytest

from tests.unit.cataloger.test_safe_sync import FakeCKAN
from wrench.models import Location, PropertyStream
from wrench.pipeline.config import PipelineRunner


@pytest.mark.parametrize("polygon", [False, True])
@pytest.mark.asyncio
async def test_yaml_pipeline_reruns_with_persisted_state(
    tmp_path, monkeypatch, make_device, polygon
):
    """Exercise actual YAML wiring, FileStore serialization and two catalog runs."""
    config = Path(__file__).parents[2] / "examples/06_observed_property.yaml"
    monkeypatch.chdir(tmp_path)
    for key, value in {
        "FROST_URL": "https://f/v1.1",
        "CKAN_URL": "https://catalog",
        "CKAN_API_KEY": "secret",
        "CKAN_OWNER_ORG": "org",
    }.items():
        monkeypatch.setenv(key, value)
    device = make_device()
    if polygon:
        device.locations = [
            Location(
                encoding_type="application/geo+json",
                location={
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [4, 0], [4, 4], [0, 0]]],
                },
            )
        ]
    device.property_streams = [
        PropertyStream(
            key="ObservedProperties:1",
            name="Temperature",
            url="https://f/v1.1/Datastreams(1)",
        )
    ]
    client = FakeCKAN()
    with (
        patch("wrench.cataloger.sddi.cataloger.RemoteCKAN", return_value=client),
        patch(
            "wrench.harvester.sensorthings.harvester.SensorThingsHarvester.return_devices",
            return_value=[device],
        ),
    ):
        first = await PipelineRunner.from_config_file(config).run({})
        assert first.success
        assert len(client.packages) == 2
        ids = set(client.packages)
        device_entry = next(
            p for p in client.packages.values() if p["type"] == "device"
        )
        assert device_entry["is_thing_group"] == "true"
        assert device_entry["is_sensor_group"] == "false"
        assert json.loads(device_entry["spatial"])["type"] == (
            "MultiPolygon" if polygon else "MultiPoint"
        )
        for package in client.packages.values():
            package["notes"] = "Edited by curator"
        second = await PipelineRunner.from_config_file(config).run({})
        assert second.success
        assert set(client.packages) == ids
        assert all(p["notes"] == "Edited by curator" for p in client.packages.values())

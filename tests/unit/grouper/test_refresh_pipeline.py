import pytest

from wrench.components.grouper import Grouper
from wrench.components.harvester import Harvester
from wrench.components.metadataenricher import MetadataEnricher
from wrench.grouper.observed_property import ObservedPropertyGrouper
from wrench.harvester.base import BaseHarvester
from wrench.metadataenricher.sensorthings import SensorThingsMetadataEnricher
from wrench.models import PropertyStream


@pytest.mark.asyncio
async def test_unchanged_source_still_refreshes_full_groups(make_device):
    device = make_device()
    device.property_streams = [
        PropertyStream(key="p", name="Temperature", url="https://f/Datastreams(1)")
    ]

    class Source(BaseHarvester):
        def return_devices(self):
            return [device]

    harvester = Harvester(Source(), always_refresh=True)
    grouper = Grouper(ObservedPropertyGrouper())
    enricher = MetadataEnricher(
        SensorThingsMetadataEnricher("https://f", "Service", "Description"),
        always_refresh=True,
    )
    first = await harvester.run()
    groups = await grouper.run(first.devices, first.operations)
    metadata = await enricher.run(first.devices, first.operations, groups.groups)
    second = await harvester.run()
    assert not second.stop_pipeline and not second.operations
    groups = await grouper.run(second.devices, second.operations)
    refreshed = await enricher.run(second.devices, second.operations, groups.groups)
    assert len(refreshed.group_metadata) == 1
    assert (
        refreshed.group_metadata[0].source_key == metadata.group_metadata[0].source_key
    )
    assert refreshed.service_metadata.source_key == "https://f|service"

from wrench.grouper.observed_property import ObservedPropertyGrouper
from wrench.harvester.sensorthings import SensorThingsHarvester
from wrench.harvester.sensorthings.models import Thing
from wrench.metadataenricher.sensorthings import SensorThingsMetadataEnricher
from wrench.models import PropertyStream


def test_properties_overlap_and_rename(make_device):
    device = make_device()
    device.property_streams = [
        PropertyStream(key="p1", name="Temperature", url="https://f/Datastreams(1)"),
        PropertyStream(key="p2", name="Humidity", url="https://f/Datastreams(2)"),
    ]
    grouper = ObservedPropertyGrouper()
    groups = grouper.group_devices([device])
    assert len(groups) == 2
    assert groups[0].endpoint_urls == ["https://f/Datastreams(1)"]
    enricher = SensorThingsMetadataEnricher("https://f", "Sensors", "Sensors")
    enricher.build_service_metadata([device])
    metadata = enricher.build_group_metadata(groups[0])
    assert metadata.title == "Temperature"
    assert metadata.temporal_extent is None
    assert enricher.content_generator is None
    device.property_streams[0].name = "Air temperature"
    assert grouper.group_devices([device])[0].source_key == groups[0].source_key


def test_harvest_preserves_typed_ids_and_both_stream_types():
    sensor = {"@iot.id": 1, "name": "s", "description": "s", "encodingType": "text"}
    prop = {
        "@iot.id": "p",
        "name": "Temperature",
        "description": "temperature",
        "definition": "https://def",
    }
    stream = {
        "@iot.id": 12,
        "name": "d",
        "description": "d",
        "Sensor": sensor,
        "unitOfMeasurement": {},
        "ObservedProperty": prop,
    }
    multi = {
        "@iot.id": "a'b",
        "name": "m",
        "description": "m",
        "Sensor": sensor,
        "unitOfMeasurements": [],
        "observationType": "x",
        "ObservedProperties": [prop],
    }
    thing = Thing.model_validate(
        {
            "@iot.id": 1,
            "name": "t",
            "description": "t",
            "Datastreams": [stream],
            "MultiDatastreams": [multi],
        }
    )
    references = SensorThingsHarvester("https://f/v1.1")._property_streams(thing)
    assert [r.url for r in references] == [
        "https://f/v1.1/Datastreams(12)",
        "https://f/v1.1/MultiDatastreams('a''b')",
    ]
    assert references[0].key == references[1].key
    assert thing.datastreams[0].observed_property.definition == "https://def"

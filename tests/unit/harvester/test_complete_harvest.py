import pytest
import requests
import responses

from wrench.harvester.sensorthings.client import SensorThingsClient


@responses.activate
def test_expanded_collection_pages_are_followed():
    client = SensorThingsClient("https://f/v1.1", None)
    item = {
        "Datastreams": [{"@iot.id": 1}],
        "Datastreams@iot.nextLink": "https://f/v1.1/Things(1)/Datastreams?$skip=1",
    }
    responses.get(item["Datastreams@iot.nextLink"], json={"value": [{"@iot.id": 2}]})
    client._expand_pages(item, "https://f/v1.1/Things")
    assert [s["@iot.id"] for s in item["Datastreams"]] == [1, 2]


@responses.activate
def test_failed_expansion_aborts():
    client = SensorThingsClient("https://f/v1.1", None)
    item = {"Datastreams": [], "Datastreams@iot.nextLink": "https://f/page2"}
    responses.get("https://f/page2", status=500)
    with pytest.raises(requests.HTTPError):
        client._expand_pages(item, "https://f/v1.1/Things")

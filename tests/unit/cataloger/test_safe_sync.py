from copy import deepcopy
from unittest.mock import patch

import pytest
from ckanapi.errors import NotFound

from wrench.cataloger.sddi import SDDICataloger
from wrench.cataloger.sddi.sync import dataset_id


class FakeCKAN:
    """In-memory Action API model; forbids destructive dataset/list replacement."""

    def __init__(self):
        self.packages = {}
        self.calls = []
        self.fail_resource_once = False

    def call_action(self, action, data_dict=None):
        d = deepcopy(data_dict or {})
        self.calls.append((action, d))
        if action == "package_show":
            if d["id"] not in self.packages:
                raise NotFound()
            return deepcopy(self.packages[d["id"]])
        if action == "package_create":
            assert d["id"] not in self.packages
            d.setdefault("resources", [])
            d.setdefault("relationships_as_subject", [])
            self.packages[d["id"]] = d
            return deepcopy(d)
        if action == "package_patch":
            assert "resources" not in d and "name" not in d and "type" not in d
            self.packages[d["id"]].update(d)
            return deepcopy(self.packages[d["id"]])
        if action == "resource_create":
            if self.fail_resource_once:
                self.fail_resource_once = False
                raise RuntimeError("network interruption")
            pkg = self.packages[d.pop("package_id")]
            d["id"] = f"resource-{len(self.calls)}"
            pkg["resources"].append(d)
            return deepcopy(d)
        if action == "resource_patch":
            for pkg in self.packages.values():
                for resource in pkg["resources"]:
                    if resource["id"] == d["id"]:
                        resource.update(d)
                        return deepcopy(resource)
            raise NotFound()
        if action == "package_relationship_create":
            self.packages[d["subject"]]["relationships_as_subject"].append(d)
            return deepcopy(d)
        raise AssertionError(action)


def catalog(client, **kwargs):
    with patch("wrench.cataloger.sddi.cataloger.RemoteCKAN", return_value=client):
        return SDDICataloger("https://catalog", "secret", "organization", **kwargs)


def test_rerun_preserves_curation_ids_and_relationships(make_common_metadata):
    client = FakeCKAN()
    service = make_common_metadata(source_key="https://f|service")
    group = make_common_metadata(
        source_key="https://f|ObservedProperties:1",
        endpoint_urls=["https://f/Datastreams(1)"],
    )
    ids = catalog(client).register(service, [group])
    pkg = client.packages[ids[1]]
    pkg.update(
        title="Manual title",
        notes="Manual description",
        author='[{"author_name":"Editor"}]',
        manufacturer="Manual manufacturer",
        private=False,
        access_rights="public",
        name="manually-renamed-slug",
        license_id="custom-license",
    )
    resource = pkg["resources"][0]
    rid = resource["id"]
    resource.update(description="Manual resource description", custom="keep")
    pkg["resources"].append({"id": "manual", "url": "https://manual"})
    group.title = "Renamed source property"
    group.spatial_extent = '{"type":"Point","coordinates":[10,20]}'
    # New cataloger and no local registry: identity comes from source, not cache.
    assert catalog(client).register(service, [group], None) == ids
    assert pkg["title"] == "Manual title" and pkg["notes"] == "Manual description"
    assert pkg["name"] == "manually-renamed-slug"
    assert pkg["manufacturer"] == "Manual manufacturer" and not pkg["private"]
    assert pkg["license_id"] == "custom-license"
    assert pkg["spatial"] == SDDICataloger._group_spatial(group.spatial_extent)
    assert pkg["resources"][0]["id"] == rid
    assert pkg["resources"][0]["description"] == "Manual resource description"
    assert pkg["resources"][1]["id"] == "manual"
    assert len(pkg["relationships_as_subject"]) == 1
    group.endpoint_urls = ["https://f/Datastreams(2)"]
    catalog(client).register(service, [group])
    assert resource["wrench_active"] == "false"
    group.endpoint_urls = ["https://f/Datastreams(1)"]
    catalog(client).register(service, [group])
    assert resource["wrench_active"] == "true" and resource["id"] == rid


def test_partial_failure_recovers_without_duplicate(make_common_metadata):
    client = FakeCKAN()
    client.fail_resource_once = True
    service = make_common_metadata(source_key="https://f|service")
    with pytest.raises(RuntimeError):
        catalog(client).register(service, [])
    catalog(client).register(service, [])
    assert len(client.packages) == 1
    assert len(client.packages[dataset_id(service.source_key)]["resources"]) == 1


def test_no_adoption_without_explicit_mapping(make_common_metadata):
    client = FakeCKAN()
    service = make_common_metadata(source_key="https://f|service")
    identity = dataset_id(service.source_key)
    client.packages[identity] = {"id": identity, "type": "online-service", "extras": []}
    with pytest.raises(ValueError, match="provenance"):
        catalog(client).register(service, [])


def test_sources_do_not_collide_and_managed_fields_opt_in(make_common_metadata):
    client = FakeCKAN()
    a = make_common_metadata(source_key="https://a|service")
    b = make_common_metadata(source_key="https://b|service")
    assert catalog(client).register(a, []) != catalog(client).register(b, [])
    a.title = "New title"
    catalog(client, managed_fields=["title"]).register(a, [])
    assert client.packages[dataset_id(a.source_key)]["title"] == "New title"

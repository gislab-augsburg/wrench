"""Conservative CKAN synchronization independent of local pipeline caches."""

from uuid import NAMESPACE_URL, uuid5

from ckanapi.errors import NotFound


def dataset_id(source_key: str) -> str:
    """Return an immutable UUID, independent of titles and grouping order."""
    return str(uuid5(NAMESPACE_URL, "wrench:dataset:" + source_key))


class CatalogSync:
    """Patch harvested fields only; never delete catalog entries or resources."""

    def __init__(self, client, managed_fields, dataset_ids):
        self.client = client
        self.managed_fields = managed_fields
        self.dataset_ids = dataset_ids

    def action(self, action, **data):
        return self.client.call_action(action=action, data_dict=data)

    def upsert(self, metadata, model):
        key = metadata.source_key
        if not key:
            raise ValueError("Stable source_key is required for safe synchronization")
        expected_id = self.dataset_ids.get(key, dataset_id(key))
        desired = model.model_dump()
        resources = desired.pop("resources", [])
        try:
            existing = self.action("package_show", id=expected_id)
        except NotFound:
            existing = None

        if existing is None:
            # A deterministic slug permits discovery even if creation succeeded but
            # the response or subsequent resource operation was interrupted.
            desired.update(
                id=expected_id,
                name="wrench-" + dataset_id(key).replace("-", ""),
                extras=[{"key": "wrench_source_key", "value": key}],
            )
            created = self.action("package_create", **desired)
            if created["id"] != expected_id:
                raise ValueError(
                    "CKAN did not retain the requested stable dataset UUID"
                )
            existing = created
        else:
            if existing.get("type") != desired["type"]:
                raise ValueError(
                    "Dataset type differs; migrate legacy dataset types explicitly"
                )
            provenance = {x["key"]: x["value"] for x in existing.get("extras", [])}
            if provenance.get("wrench_source_key") != key:
                # Legacy adoption must be explicit, never inferred from a title.
                if (
                    self.dataset_ids.get(key) != existing["id"]
                    or "wrench_source_key" in provenance
                ):
                    raise ValueError("Refusing update: different or missing provenance")
                provenance["wrench_source_key"] = key
                self.action(
                    "package_patch",
                    id=existing["id"],
                    extras=[{"key": k, "value": v} for k, v in provenance.items()],
                )
            changes = {
                k: desired[k]
                for k in self.managed_fields
                if k in desired and existing.get(k) != desired[k]
            }
            if changes:
                self.action("package_patch", id=existing["id"], **changes)

        self.sync_resources(existing, resources)
        return existing

    def sync_resources(self, package, desired):
        # Independent resource actions avoid replacing lists of manually added
        # resources and preserve names, descriptions, custom fields, and IDs.
        managed = {}
        for resource in package.get("resources", []):
            key = resource.get("wrench_source_key")
            if key:
                if key in managed:
                    raise ValueError("Duplicate managed resource identity")
                managed[key] = resource
        active_keys = set()
        for resource in desired:
            key = "endpoint:" + resource["url"]
            active_keys.add(key)
            existing = managed.get(key)
            if existing is None:
                self.action(
                    "resource_create",
                    package_id=package["id"],
                    wrench_source_key=key,
                    wrench_active="true",
                    **resource,
                )
            else:
                patch = {"url": resource["url"], "wrench_active": "true"}
                patch = {k: v for k, v in patch.items() if existing.get(k) != v}
                if patch:
                    self.action("resource_patch", id=existing["id"], **patch)
        for key, resource in managed.items():
            if key not in active_keys and resource.get("wrench_active") != "false":
                self.action("resource_patch", id=resource["id"], wrench_active="false")

    def relate(self, group, service):
        for relationship in group.get("relationships_as_subject", []):
            if relationship.get("type") == "links_to" and relationship.get(
                "object"
            ) in {service["id"], service["name"]}:
                return
        self.action(
            "package_relationship_create",
            subject=group["id"],
            object=service["id"],
            type="links_to",
        )

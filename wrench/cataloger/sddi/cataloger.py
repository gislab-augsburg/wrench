from datetime import datetime
from typing import Literal
from urllib.parse import urlsplit

from ckanapi import RemoteCKAN

from wrench.cataloger.base import BaseCataloger
from wrench.models import CommonMetadata

from .models import DeviceGroup, OnlineService

DEFAULT_OWNER = "lehrstuhl-fur-geoinformatik"


class SDDICataloger(BaseCataloger):
    """
    Interact with a SDDI CKAN server to register and manage datasets.

    :param url: The URL of the SDDI CKAN server.
    :param api_key: The API key for authenticating with the SDDI CKAN server.
    """

    def __init__(
        self,
        base_url: str,
        api_key: str,
        owner_org: str = "lehrstuhl-fur-geoinformatik",
        license_id: str = "notspecified",
        managed_fields: list[str] | None = None,
        dataset_ids: dict[str, str] | None = None,
        status: Literal["draft", "active"] = "draft",
        access_rights: Literal["private", "public"] = "private",
    ):
        """
        Initialize the register with the given configuration.

        Args:
            base_url (str): Base URL of the SDDI catalog to register to.
            api_key (str): API Key for registration authorization.
            owner_org (str): Owner organization to which the dataset will belong to.
            license_id: Source-data license for new entries.
            status: Metadata status for new entries.
            access_rights: Visibility for new entries.
            managed_fields: Harvested fields that may change on existing entries.
            dataset_ids: Explicit source-key to UUID mappings for legacy adoption.

        Raises:
            ValueError: If the provided configuration path is invalid or the
                configuration file cannot be loaded.

        """
        super().__init__(endpoint=base_url, api_key=api_key)

        self.ckan_server = RemoteCKAN(address=self.endpoint, apikey=self.api_key)
        self.owner_org = owner_org
        self.license_id = license_id
        defaults = {
            "spatial",
            "begin_collection_date",
            "end_collection_date",
            "observed_property",
            "is_thing_group",
        }
        allowed = defaults | {
            "is_sensor_group",
            "title",
            "notes",
            "tags",
            "protocol",
            "service_standard",
            "response_formats",
            "service_type",
            "http_method",
        }
        self.managed_fields = (
            set(managed_fields) if managed_fields is not None else defaults
        )
        if self.managed_fields - allowed:
            raise ValueError(
                "Unsupported managed field; cannot manage identity, owner or access"
            )
        self.dataset_ids = dataset_ids or {}
        if status not in {"draft", "active"} or access_rights not in {
            "private",
            "public",
        }:
            raise ValueError("Invalid SDDI status or access_rights")
        self.status = status
        self.access_rights = access_rights
        self._registries: set[str] = set()

    def register(self, service, groups, managed_entries=None) -> list[str]:
        """Discover by stable UUID and preserve catalog-owned fields on updates."""
        from .sync import CatalogSync

        sync = CatalogSync(self.ckan_server, self.managed_fields, self.dataset_ids)
        # Validate every group before making any CKAN writes.
        device_groups = self._create_device_groups(groups)
        service_entry = sync.upsert(service, self._create_online_service(service))
        registered = [service_entry["id"]]
        for metadata, model in zip(groups, device_groups):
            entry = sync.upsert(metadata, model)
            sync.relate(entry, service_entry)
            registered.append(entry["id"])
        return registered

    def _get_package(self, package_id: str):
        pkg = self.ckan_server.call_action(
            action="package_show", data_dict={"id": package_id}
        )
        return pkg

    def _register_api_service(self, api_service: OnlineService):
        self._registries.add(api_service.name)
        pkg = self.ckan_server.call_action(
            action="package_create", data_dict=api_service.model_dump()
        )
        return pkg

    def _register_device_group(self, device_group: DeviceGroup):
        self._registries.add(device_group.name)
        pkg = self.ckan_server.call_action(
            action="package_create",
            data_dict=device_group.model_dump(),
        )
        return pkg

    def _update_api_service(self, api_service: OnlineService):
        pkg = self.ckan_server.call_action(
            action="package_patch",
            data_dict={**api_service.model_dump(), "id": api_service.name},
        )
        return pkg

    def _update_device_group(self, device_group: DeviceGroup):
        pkg = self.ckan_server.call_action(
            action="package_patch",
            data_dict={**device_group.model_dump(), "id": device_group.name},
        )
        return pkg

    def _register_relationship(self, api_service_name: str, device_group_name: str):
        rel = self.ckan_server.call_action(
            action="package_relationship_create",
            data_dict={
                "subject": device_group_name,
                "object": api_service_name,
                "type": "links_to",
            },
        )
        return rel

    def delete_resource(self, dataset_name: str):
        self.ckan_server.call_action(
            action="dataset_purge", data_dict={"id": dataset_name}
        )
        self.logger.info("successfully deleted resource")

    def get_owner_orgs(self) -> list[str]:
        return self.ckan_server.call_action(
            action="organization_list",
        )

    def _create_online_service(self, metadata: CommonMetadata) -> OnlineService:
        return OnlineService(
            url=metadata.endpoint_urls[0],
            name=metadata.identifier,
            notes=metadata.description,
            owner_org=metadata.owner or self.owner_org,
            title=metadata.title,
            tags=[{"name": tag} for tag in metadata.tags or ["sensorthings"]],
            spatial=metadata.spatial_extent,
            license_id=self.license_id,
            status=self.status,
            access_rights=self.access_rights,
            private=self.access_rights == "private",
            service_type="RESTful",
            service_standard="REST",
            http_method="GET",
            protocol=urlsplit(metadata.endpoint_urls[0]).scheme.upper(),
            begin_collection_date=metadata.temporal_extent.start_time.strftime(
                "%Y-%m-%d"
            )
            if metadata.temporal_extent
            else "",
            end_collection_date=metadata.temporal_extent.latest_time.strftime(
                "%Y-%m-%d"
            )
            if metadata.temporal_extent
            else "",
        )

    def _create_device_groups(
        self, metadata: list[CommonMetadata]
    ) -> list[DeviceGroup]:
        device_groups: list[DeviceGroup] = []

        for group in metadata:
            start_date, latest_date = "", ""

            if group.temporal_extent:
                start_date = group.temporal_extent.start_time.strftime("%Y-%m-%d")
                latest_date = group.temporal_extent.latest_time.strftime("%Y-%m-%d")

            if (
                group.temporal_extent is not None
                and group.temporal_extent.latest_time.date() == datetime.today().date()
            ):
                latest_date = ""

            try:
                spatial = self._group_spatial(
                    group.spatial_extent, group.is_sensor_group
                )
            except ValueError as error:
                raise ValueError(
                    f"Group {group.source_key or group.identifier}: {error}"
                ) from error

            device_group = DeviceGroup(
                url=group.endpoint_urls[0],
                name=group.identifier,
                notes=group.description,
                owner_org=group.owner or self.owner_org,
                begin_collection_date=start_date,
                end_collection_date=latest_date,
                title=group.title,
                tags=[{"name": tag} for tag in group.tags or ["sensorthings", "thing"]],
                spatial=spatial,
                license_id=self.license_id,
                status=self.status,
                access_rights=self.access_rights,
                private=self.access_rights == "private",
                observed_property=group.observed_property,
                is_sensor_group="true" if group.is_sensor_group else "false",
                service_standard="OGC_SensorThings",
                response_formats="JSON",
                protocol=urlsplit(group.endpoint_urls[0]).scheme.upper(),
                resources=[
                    {
                        "name": f"URL-{i} for {group.title}",
                        "description": f"URL provides data for group: {group.title}",
                        "format": "JSON",
                        "url": url,
                    }
                    for i, url in enumerate(group.endpoint_urls)
                ],
            )
            device_groups.append(device_group)

        return device_groups

    @staticmethod
    def _group_spatial(spatial: str, sensor_group: bool = False) -> str:
        from .spatial import group_spatial

        return group_spatial(spatial, sensor_group)

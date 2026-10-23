from enum import Enum

from pydantic import BaseModel, Field, computed_field

from wrench.utils.sanitization import sanitize_ckan_name


class SDDICategory(Enum):
    online_service = "online-service"
    device = "device"


class SDDIDataset(BaseModel):
    # required
    name: str = Field(serialization_alias="name")  # use "name" for the JSON payload
    title: str = Field(serialization_alias="title")
    notes: str = Field(serialization_alias="notes")
    owner_org: str
    # optional with predefined defaults
    url: str | None = None
    # SDDI composite fields are JSON-encoded lists, not flat author strings.
    author: str = ""
    maintainer: str = ""
    status: str = "draft"
    access_rights: str = "private"
    service_standard: str = ""
    protocol: str = ""
    observed_property: str = ""
    is_sensor_group: str = "false"
    response_formats: str = ""
    service_type: str = ""
    http_method: str = ""
    begin_collection_date: str = ""
    end_collection_date: str = ""  # necessary to properly register entries
    groups: list[dict] = []
    language: str = ""
    licence_agreement: list[str] = ["licence_agreement_check"]
    license_id: str = "notspecified"
    private: bool = True
    relationships_as_object: list[dict] = []
    relationships_as_subject: list[dict] = []
    spatial: str = ""
    state: str = "active"
    tags: list[dict] = []
    type: str = "dataset"

    def model_dump(self, **kwargs):
        """Override to ensure serialization aliases are used by default."""
        kwargs.setdefault("by_alias", True)
        return super().model_dump(**kwargs)


class OnlineService(SDDIDataset):
    type: str = "online-service"
    groups: list[dict] = []

    @computed_field  # type: ignore[misc]
    @property
    def resources(self) -> list[dict]:
        return [
            {
                "name": "API Service URL",
                "description": "URL for the API service",
                "format": "JSON",
                "linkage": self.url,
                "mime_type": "application/json",
                "url": self.url,
            }
        ]


class DeviceGroup(SDDIDataset):
    type: str = "device"
    is_thing_group: str = "true"
    groups: list[dict] = []
    resources: list[dict] = []

    @classmethod
    def from_api_service(
        cls,
        online_service: OnlineService,
        name: str,
        description: str,
        tags: list[dict[str, str]],
        resources: list = [],
    ) -> "DeviceGroup":
        # Get all fields from api_service except 'groups' and 'resources'
        ckan_name = sanitize_ckan_name(name, fallback_prefix="device_group")
        data = online_service.model_dump(exclude={"groups", "resources"})
        data.update(
            {
                "id": ckan_name,
                "name": name,
                "description": description,
                "tags": tags,
                "resources": resources or [],
            }
        )
        return cls(**data)

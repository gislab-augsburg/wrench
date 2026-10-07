import time
from typing import Generator
from urllib.parse import urljoin

import requests

from wrench.log import logger

from .config import PaginationConfig
from .models import SensorThingsBase, Thing

ENDPOINT = """
Things?$expand=Locations,
Datastreams($expand=Sensor,ObservedProperty)
"""

ENDPOINT_WITH_MULTIDATASTREAM = """
Things?$expand=Locations,
Datastreams($expand=Sensor,ObservedProperty),
MultiDatastreams($expand=Sensor,ObservedProperties)
"""


class SensorThingsClient:
    """
    Retrieves items from SensorThings API.

    SensorThingsClient handles the pagination of items in the SensorThingsAPI server and
    fetches Things with expanded Datastreams, Sensor, and Locations as Items
    """

    def __init__(self, base_url: str, config: PaginationConfig | None):
        """
        Initializes a SensorThings API client.

        Args:
            base_url (str): The base URL of the server to fetch from
            config (PaginationConfig): The pagination config to use
        """
        self.base_url = base_url.rstrip("/")
        self.config = config if config else PaginationConfig()
        self.logger = logger.getChild(self.__class__.__name__)

    def fetch_things(self, limit: int = -1) -> list[Thing]:
        """
        Fetches a list of Thing objects.

        Args:
            limit (int): Max number of Things to fetch. Defaults to -1 (no limit).

        Returns:
            list[Thing]: List of fetched Things.
        """
        self.logger.debug(f"Fetching {limit if limit != -1 else 'all'} things")

        endpoint = (
            ENDPOINT
            if not self._check_multidatastream()
            else ENDPOINT_WITH_MULTIDATASTREAM
        )

        # Simply collect all items from the generator
        things = list(self._paginate(endpoint, Thing, limit))

        self.logger.info(f"Finished fetching data, retrieved {len(things)} items")
        return things

    def _paginate[T: SensorThingsBase](
        self, endpoint: str, model_class: type[T], limit: int = -1
    ) -> Generator[T, None, None]:
        """
        Simple generator that yields items from a paginated API.

        Args:
            endpoint: API endpoint path to fetch from
            model_class: Pydantic model class to validate response data
            limit: Maximum number of items to fetch (-1 for no limit)

        Yields:
            Validated model instances one at a time
        """
        endpoint = "".join(endpoint.split())
        url = f"{self.base_url}/{endpoint}"
        visited = set()
        items_fetched = 0
        page_count = 0

        while url and (limit == -1 or items_fetched < limit):
            if url in visited:
                raise ValueError("Repeated SensorThings pagination URL")
            visited.add(url)
            page_count += 1
            self.logger.info(f"Fetching page {page_count}")

            try:
                # Fetch the page
                response = requests.get(url, timeout=self.config.timeout)
                response.raise_for_status()
                data = response.json()

                # Check for valid response
                if "value" not in data:
                    raise ValueError("SensorThings page has no value collection")

                # Process and yield each item
                items_on_page = 0
                for item in data["value"]:
                    if limit != -1 and items_fetched >= limit:
                        break

                    try:
                        self._expand_pages(item, url)
                        validated_item = model_class.model_validate(item)
                        yield validated_item
                        items_fetched += 1
                        items_on_page += 1
                    except Exception as e:
                        raise ValueError(
                            "Invalid SensorThings item; refusing partial harvest"
                        ) from e

                self.logger.info(
                    f"Processed {items_on_page} items from page {page_count}"
                )

                # Get the next page URL
                next_link = data.get("@iot.nextLink")
                url = urljoin(url, next_link) if next_link else None
                if url and (limit == -1 or items_fetched < limit):
                    time.sleep(self.config.page_delay)

            except requests.RequestException as e:
                self.logger.error(f"Failed to fetch page {page_count}: {str(e)}")
                raise

    def _check_multidatastream(self) -> bool:
        multidatastream_endpoint = "MultiDatastreams"
        res = requests.get(
            f"{self.base_url}/{multidatastream_endpoint}", timeout=self.config.timeout
        )
        if res.status_code in (400, 404):
            return False
        res.raise_for_status()
        return True

    def _expand_pages(self, item, base_url):
        """Load all pages of expanded collections before accepting a Thing."""
        for name in list(item):
            if name.endswith("@iot.nextLink") and name != "@iot.nextLink":
                collection = name.removesuffix("@iot.nextLink")
                link = item.pop(name)
                visited = set()
                while link:
                    url = urljoin(base_url, link)
                    if url in visited:
                        raise ValueError("Repeated expanded collection page")
                    visited.add(url)
                    response = requests.get(url, timeout=self.config.timeout)
                    response.raise_for_status()
                    page = response.json()
                    item.setdefault(collection, []).extend(page["value"])
                    link = page.get("@iot.nextLink")
                    base_url = url
        for value in item.values():
            if isinstance(value, list):
                for child in value:
                    if isinstance(child, dict):
                        self._expand_pages(child, base_url)
            elif isinstance(value, dict):
                self._expand_pages(value, base_url)

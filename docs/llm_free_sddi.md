# FROST to typed SDDI catalogs without an LLM

Use Python 3.12+ and install the repository with `pip install -e .`.
The ObservedProperty path does not load KINETIC, embeddings or an LLM client.
The base dependency list still includes the OpenAI SDK for compatibility with existing users;
no LLM credentials, endpoint, model downloads or inference calls are needed for this path.

## Run

Set `FROST_URL` to the SensorThings API root (e.g. `https://host/FROST-Server/v1.1`),
`CKAN_URL`, `CKAN_API_KEY`, and `CKAN_OWNER_ORG`. Use
`examples/06_observed_property.yaml`:

```python
import asyncio
from wrench.pipeline.config import PipelineRunner

runner = PipelineRunner.from_config_file("examples/06_observed_property.yaml")
result = asyncio.run(runner.run({}))
if not result.success:
    raise RuntimeError("Pipeline failed; inspect component errors before retrying")
```

The target must load `sddi_device.yaml` and `sddi_online_service.yaml` from
ckanext-scheme-sddi and support CKAN's `links_to` relationship.
Service entries use type `online-service`; property groups use type `device`.
There is no dependency on category groups named `online-service` or `device`.
Tags are supplied even when there is no topic hierarchy.

Defaults are **private**, status **draft**, license **notspecified**. Verify this license
ID exists on the target, or set `license_id` in the cataloger configuration to the
actual source-data license. To publish new records intentionally, configure
`status: active` and `access_rights: public`. Access and license settings are creation
defaults; reruns preserve the catalog's values.

## Grouping

One group per source-local ObservedProperty ID. Different IDs are not merged just
because their labels or definitions match. A Thing may appear in several groups.
Names and descriptions come from the source; stream URLs are built from typed IDs,
including correctly escaped string IDs. Properties without matching streams do not
produce groups. MultiDatastream URLs expose the full vector observation, including
its other properties; this importer does not project individual vector components.
Time ranges are calculated from matching streams. Missing dates/locations are omitted.
Sensor groups with locations must have point or MultiPoint locations for the SDDI
MultiPoint constraint; non-point locations raise an error instead of inventing positions.
The online-service schema does not offer OGC_SensorThings, so service_standard is REST;
device groups use OGC_SensorThings. No changes to the schema repository are required.

## Stable identity and conservative updates

Dataset source keys are `<FROST_URL without trailing slash>|service` and
`<FROST_URL>|ObservedProperties:<JSON-encoded original ID>` (numeric and string IDs
remain distinct). UUIDv5 derives CKAN dataset IDs and initial slugs from these keys.
The key is also stored in the `wrench_source_key` dataset extra. Titles are not identities.
Changing the source URL or property ID creates a new identity; configure an explicit
migration if the upstream server renumbers entities. Normalized trailing slashes match.

Each run fetches the complete source and recomputes deterministic groups. It finds
CKAN entries by UUID even after local cache loss or a manual slug rename. Failed writes
propagate; retries discover already-created records. CKAN must retain caller-supplied
dataset UUIDs and dataset/resource provenance fields. Validate this with a staging catalog.

Updates manage only `spatial`, `begin_collection_date`, `end_collection_date`,
`observed_property`, and `is_sensor_group` by default. Titles, descriptions, authors,
maintainers, tags, licenses, access settings and other curated fields survive updates.
An optional `managed_fields` list replaces these defaults; use it to opt in to generated
titles/notes or other supported fields. Identity, ownership and access cannot be managed
through this option. Concurrent changes to managed fields may be overwritten; run one
writer per source and keep editorial fields out of the managed list.

Resources are identified by source endpoint in `wrench_source_key`. Existing resources
are patched by CKAN resource ID without replacing the package's resource list. Manual
resource descriptions and additional resources are preserved. Missing endpoints are
retained with `wrench_active: "false"`; reappearing endpoints reuse their resource IDs.
Groups no longer present are retained unchanged for editorial review, never purged.
Run one synchronizer per source at a time to avoid concurrent resource creation races.

Legacy datasets created by title-based Wrench are **not automatically adopted**.
After explicitly migrating their schema type, configure `dataset_ids` as a mapping from
the new source key to the existing CKAN UUID to adopt them. Existing resources without
provenance remain untouched; matching imported resources will be created separately.
Never infer adoption from similar titles. Keep this migration mapping for future runs.

The ML groupers remain available, but names from changing clusters cannot provide the
same semantic stability as ObservedProperty IDs. These guarantees target the deterministic
ObservedProperty pipeline. Failed/incomplete SensorThings pages abort the harvest; nested
expanded collections are paginated rather than silently truncated.

"""Deterministic SensorThings grouping, without models or external services."""

from wrench.models import Device, Group, TimeFrame

from .base import BaseGrouper


class ObservedPropertyGrouper(BaseGrouper):
    """Group by source ObservedProperty ID; a Thing may belong to several groups."""

    full_refresh = True

    def group_devices(self, devices: list[Device], **kwargs) -> list[Group]:
        buckets = {}
        for device in sorted(devices, key=lambda d: d.id):
            by_property = {}
            for stream in device.property_streams:
                by_property.setdefault(stream.key, []).append(stream)
            for key, streams in sorted(by_property.items()):
                group = buckets.setdefault(
                    key,
                    Group(
                        source_key=key,
                        name=streams[0].name,
                        description=streams[0].description,
                        observed_property=streams[0].name,
                        devices=[],
                    ),
                )
                times = [s.time_frame for s in streams if s.time_frame]
                timeframe = (
                    TimeFrame(
                        start_time=min(t.start_time for t in times),
                        latest_time=max(t.latest_time for t in times),
                    )
                    if times
                    else None
                )
                group.devices.append(
                    device.model_copy(update={"time_frame": timeframe})
                )
                group.endpoint_urls = sorted(
                    set(group.endpoint_urls) | {s.url for s in streams}
                )
        return [buckets[key] for key in sorted(buckets)]

"""Grouping implementations; optional ML dependencies load only when selected."""

from importlib import import_module

from .base import BaseGrouper
from .observed_property import ObservedPropertyGrouper

GROUPERS = {"observed_property": ObservedPropertyGrouper}
OPTIONAL_GROUPERS = {
    "kinetic": ("wrench.grouper.kinetic", "KINETIC"),
    "lda": ("wrench.grouper.lda", "LDAGrouper"),
    "bertopic": ("wrench.grouper.bertopic", "BERTopicGrouper"),
}


def get_grouper(name):
    """Resolve an explicitly selected implementation."""
    if name in OPTIONAL_GROUPERS:
        module, attr = OPTIONAL_GROUPERS[name]
        return getattr(import_module(module), attr)
    return GROUPERS[name]


def __getattr__(name):
    if name == "KINETIC":
        return get_grouper("kinetic")
    raise AttributeError(name)


__all__ = ["BaseGrouper", "ObservedPropertyGrouper", "GROUPERS", "KINETIC"]

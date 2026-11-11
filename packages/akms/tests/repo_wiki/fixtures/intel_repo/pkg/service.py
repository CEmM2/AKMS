"""Services built on the core helpers."""

from pkg import core
from pkg.core import Store, middle


def run(value):
    return middle(value)


def persist(item):
    store = Store()
    return store.save(item)


def via_module(value):
    return core.leaf(value)


def persist_any(store, item):
    """Save through whichever store is passed in."""
    return store.save(item)

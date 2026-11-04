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

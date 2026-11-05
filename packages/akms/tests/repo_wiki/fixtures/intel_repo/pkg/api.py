"""Public API."""

from pkg.service import run


def public_entry(value):
    """Run the service."""
    return run(value)

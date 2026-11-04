"""Core helpers."""


def leaf(value):
    """Return the value doubled."""
    return value * 2


def middle(value):
    return leaf(value) + 1


def parse(text):
    return text.strip()


class Store:
    """Keeps items."""

    def save(self, item):
        return self._write(item)

    def _write(self, item):
        return leaf(item)

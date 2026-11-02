"""Tiny fixture module."""

VALUE = 3


class Greeter:
    """Creates greeting messages."""

    def __init__(self, name: str) -> None:
        self.name = name

    def greet(self) -> str:
        """Return a friendly greeting."""
        return helper(self.name)


def helper(name: str) -> str:
    return f"Hello, {name}"

"""Module 39 of the perf fixture."""


CONST_39 = 39


def func_39_1(x: int, y: int) -> int:
    """Compute step 1 for module 39."""
    return x + y + CONST_39 + 1


def func_39_2(x: int, y: int) -> int:
    """Compute step 2 for module 39."""
    return x + y + CONST_39 + 2


def func_39_3(x: int, y: int) -> int:
    """Compute step 3 for module 39."""
    return x + y + CONST_39 + 3


class Worker_39:
    """A worker class for module 39."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 39."""
        return f"{self.name}-39"

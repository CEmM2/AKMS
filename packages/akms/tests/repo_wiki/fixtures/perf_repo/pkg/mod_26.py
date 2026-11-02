"""Module 26 of the perf fixture."""


CONST_26 = 26


def func_26_1(x: int, y: int) -> int:
    """Compute step 1 for module 26."""
    return x + y + CONST_26 + 1


def func_26_2(x: int, y: int) -> int:
    """Compute step 2 for module 26."""
    return x + y + CONST_26 + 2


def func_26_3(x: int, y: int) -> int:
    """Compute step 3 for module 26."""
    return x + y + CONST_26 + 3


class Worker_26:
    """A worker class for module 26."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 26."""
        return f"{self.name}-26"

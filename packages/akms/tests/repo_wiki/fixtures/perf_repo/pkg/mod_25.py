"""Module 25 of the perf fixture."""


CONST_25 = 25


def func_25_1(x: int, y: int) -> int:
    """Compute step 1 for module 25."""
    return x + y + CONST_25 + 1


def func_25_2(x: int, y: int) -> int:
    """Compute step 2 for module 25."""
    return x + y + CONST_25 + 2


def func_25_3(x: int, y: int) -> int:
    """Compute step 3 for module 25."""
    return x + y + CONST_25 + 3


class Worker_25:
    """A worker class for module 25."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 25."""
        return f"{self.name}-25"

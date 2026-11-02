"""Module 35 of the perf fixture."""


CONST_35 = 35


def func_35_1(x: int, y: int) -> int:
    """Compute step 1 for module 35."""
    return x + y + CONST_35 + 1


def func_35_2(x: int, y: int) -> int:
    """Compute step 2 for module 35."""
    return x + y + CONST_35 + 2


def func_35_3(x: int, y: int) -> int:
    """Compute step 3 for module 35."""
    return x + y + CONST_35 + 3


class Worker_35:
    """A worker class for module 35."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 35."""
        return f"{self.name}-35"

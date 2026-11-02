"""Module 12 of the perf fixture."""


CONST_12 = 12


def func_12_1(x: int, y: int) -> int:
    """Compute step 1 for module 12."""
    return x + y + CONST_12 + 1


def func_12_2(x: int, y: int) -> int:
    """Compute step 2 for module 12."""
    return x + y + CONST_12 + 2


def func_12_3(x: int, y: int) -> int:
    """Compute step 3 for module 12."""
    return x + y + CONST_12 + 3


class Worker_12:
    """A worker class for module 12."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 12."""
        return f"{self.name}-12"

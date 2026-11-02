"""Module 05 of the perf fixture."""


CONST_05 = 5


def func_05_1(x: int, y: int) -> int:
    """Compute step 1 for module 05."""
    return x + y + CONST_05 + 1


def func_05_2(x: int, y: int) -> int:
    """Compute step 2 for module 05."""
    return x + y + CONST_05 + 2


def func_05_3(x: int, y: int) -> int:
    """Compute step 3 for module 05."""
    return x + y + CONST_05 + 3


class Worker_05:
    """A worker class for module 05."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 05."""
        return f"{self.name}-05"

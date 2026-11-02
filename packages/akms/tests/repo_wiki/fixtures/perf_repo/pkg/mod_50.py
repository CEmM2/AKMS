"""Module 50 of the perf fixture."""


CONST_50 = 50


def func_50_1(x: int, y: int) -> int:
    """Compute step 1 for module 50."""
    return x + y + CONST_50 + 1


def func_50_2(x: int, y: int) -> int:
    """Compute step 2 for module 50."""
    return x + y + CONST_50 + 2


def func_50_3(x: int, y: int) -> int:
    """Compute step 3 for module 50."""
    return x + y + CONST_50 + 3


class Worker_50:
    """A worker class for module 50."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 50."""
        return f"{self.name}-50"

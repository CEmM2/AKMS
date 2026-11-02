"""Module 07 of the perf fixture."""


CONST_07 = 7


def func_07_1(x: int, y: int) -> int:
    """Compute step 1 for module 07."""
    return x + y + CONST_07 + 1


def func_07_2(x: int, y: int) -> int:
    """Compute step 2 for module 07."""
    return x + y + CONST_07 + 2


def func_07_3(x: int, y: int) -> int:
    """Compute step 3 for module 07."""
    return x + y + CONST_07 + 3


class Worker_07:
    """A worker class for module 07."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 07."""
        return f"{self.name}-07"

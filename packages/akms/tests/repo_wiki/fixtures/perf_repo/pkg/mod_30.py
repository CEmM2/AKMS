"""Module 30 of the perf fixture."""


CONST_30 = 30


def func_30_1(x: int, y: int) -> int:
    """Compute step 1 for module 30."""
    return x + y + CONST_30 + 1


def func_30_2(x: int, y: int) -> int:
    """Compute step 2 for module 30."""
    return x + y + CONST_30 + 2


def func_30_3(x: int, y: int) -> int:
    """Compute step 3 for module 30."""
    return x + y + CONST_30 + 3


class Worker_30:
    """A worker class for module 30."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 30."""
        return f"{self.name}-30"

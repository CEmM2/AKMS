"""Module 17 of the perf fixture."""


CONST_17 = 17


def func_17_1(x: int, y: int) -> int:
    """Compute step 1 for module 17."""
    return x + y + CONST_17 + 1


def func_17_2(x: int, y: int) -> int:
    """Compute step 2 for module 17."""
    return x + y + CONST_17 + 2


def func_17_3(x: int, y: int) -> int:
    """Compute step 3 for module 17."""
    return x + y + CONST_17 + 3


class Worker_17:
    """A worker class for module 17."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 17."""
        return f"{self.name}-17"

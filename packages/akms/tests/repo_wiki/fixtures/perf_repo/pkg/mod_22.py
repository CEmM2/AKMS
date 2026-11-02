"""Module 22 of the perf fixture."""


CONST_22 = 22


def func_22_1(x: int, y: int) -> int:
    """Compute step 1 for module 22."""
    return x + y + CONST_22 + 1


def func_22_2(x: int, y: int) -> int:
    """Compute step 2 for module 22."""
    return x + y + CONST_22 + 2


def func_22_3(x: int, y: int) -> int:
    """Compute step 3 for module 22."""
    return x + y + CONST_22 + 3


class Worker_22:
    """A worker class for module 22."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 22."""
        return f"{self.name}-22"

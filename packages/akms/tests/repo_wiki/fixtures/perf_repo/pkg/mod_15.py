"""Module 15 of the perf fixture."""


CONST_15 = 15


def func_15_1(x: int, y: int) -> int:
    """Compute step 1 for module 15."""
    return x + y + CONST_15 + 1


def func_15_2(x: int, y: int) -> int:
    """Compute step 2 for module 15."""
    return x + y + CONST_15 + 2


def func_15_3(x: int, y: int) -> int:
    """Compute step 3 for module 15."""
    return x + y + CONST_15 + 3


class Worker_15:
    """A worker class for module 15."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 15."""
        return f"{self.name}-15"

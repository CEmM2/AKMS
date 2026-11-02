"""Module 20 of the perf fixture."""


CONST_20 = 20


def func_20_1(x: int, y: int) -> int:
    """Compute step 1 for module 20."""
    return x + y + CONST_20 + 1


def func_20_2(x: int, y: int) -> int:
    """Compute step 2 for module 20."""
    return x + y + CONST_20 + 2


def func_20_3(x: int, y: int) -> int:
    """Compute step 3 for module 20."""
    return x + y + CONST_20 + 3


class Worker_20:
    """A worker class for module 20."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 20."""
        return f"{self.name}-20"

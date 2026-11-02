"""Module 09 of the perf fixture."""


CONST_09 = 9


def func_09_1(x: int, y: int) -> int:
    """Compute step 1 for module 09."""
    return x + y + CONST_09 + 1


def func_09_2(x: int, y: int) -> int:
    """Compute step 2 for module 09."""
    return x + y + CONST_09 + 2


def func_09_3(x: int, y: int) -> int:
    """Compute step 3 for module 09."""
    return x + y + CONST_09 + 3


class Worker_09:
    """A worker class for module 09."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 09."""
        return f"{self.name}-09"

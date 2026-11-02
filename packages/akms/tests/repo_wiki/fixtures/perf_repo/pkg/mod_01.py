"""Module 01 of the perf fixture."""


CONST_01 = 1


def func_01_1(x: int, y: int) -> int:
    """Compute step 1 for module 01."""
    return x + y + CONST_01 + 1


def func_01_2(x: int, y: int) -> int:
    """Compute step 2 for module 01."""
    return x + y + CONST_01 + 2


def func_01_3(x: int, y: int) -> int:
    """Compute step 3 for module 01."""
    return x + y + CONST_01 + 3


class Worker_01:
    """A worker class for module 01."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 01."""
        return f"{self.name}-01"

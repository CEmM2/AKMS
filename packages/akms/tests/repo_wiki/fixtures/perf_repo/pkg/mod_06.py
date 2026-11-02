"""Module 06 of the perf fixture."""


CONST_06 = 6


def func_06_1(x: int, y: int) -> int:
    """Compute step 1 for module 06."""
    return x + y + CONST_06 + 1


def func_06_2(x: int, y: int) -> int:
    """Compute step 2 for module 06."""
    return x + y + CONST_06 + 2


def func_06_3(x: int, y: int) -> int:
    """Compute step 3 for module 06."""
    return x + y + CONST_06 + 3


class Worker_06:
    """A worker class for module 06."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 06."""
        return f"{self.name}-06"

"""Module 03 of the perf fixture."""


CONST_03 = 3


def func_03_1(x: int, y: int) -> int:
    """Compute step 1 for module 03."""
    return x + y + CONST_03 + 1


def func_03_2(x: int, y: int) -> int:
    """Compute step 2 for module 03."""
    return x + y + CONST_03 + 2


def func_03_3(x: int, y: int) -> int:
    """Compute step 3 for module 03."""
    return x + y + CONST_03 + 3


class Worker_03:
    """A worker class for module 03."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 03."""
        return f"{self.name}-03"

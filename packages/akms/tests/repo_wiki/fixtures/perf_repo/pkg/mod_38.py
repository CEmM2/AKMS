"""Module 38 of the perf fixture."""


CONST_38 = 38


def func_38_1(x: int, y: int) -> int:
    """Compute step 1 for module 38."""
    return x + y + CONST_38 + 1


def func_38_2(x: int, y: int) -> int:
    """Compute step 2 for module 38."""
    return x + y + CONST_38 + 2


def func_38_3(x: int, y: int) -> int:
    """Compute step 3 for module 38."""
    return x + y + CONST_38 + 3


class Worker_38:
    """A worker class for module 38."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 38."""
        return f"{self.name}-38"

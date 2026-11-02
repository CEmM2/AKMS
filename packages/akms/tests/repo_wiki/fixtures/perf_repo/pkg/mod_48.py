"""Module 48 of the perf fixture."""


CONST_48 = 48


def func_48_1(x: int, y: int) -> int:
    """Compute step 1 for module 48."""
    return x + y + CONST_48 + 1


def func_48_2(x: int, y: int) -> int:
    """Compute step 2 for module 48."""
    return x + y + CONST_48 + 2


def func_48_3(x: int, y: int) -> int:
    """Compute step 3 for module 48."""
    return x + y + CONST_48 + 3


class Worker_48:
    """A worker class for module 48."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 48."""
        return f"{self.name}-48"

"""Module 49 of the perf fixture."""


CONST_49 = 49


def func_49_1(x: int, y: int) -> int:
    """Compute step 1 for module 49."""
    return x + y + CONST_49 + 1


def func_49_2(x: int, y: int) -> int:
    """Compute step 2 for module 49."""
    return x + y + CONST_49 + 2


def func_49_3(x: int, y: int) -> int:
    """Compute step 3 for module 49."""
    return x + y + CONST_49 + 3


class Worker_49:
    """A worker class for module 49."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 49."""
        return f"{self.name}-49"

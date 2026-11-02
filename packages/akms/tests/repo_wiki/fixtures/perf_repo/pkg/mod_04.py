"""Module 04 of the perf fixture."""


CONST_04 = 4


def func_04_1(x: int, y: int) -> int:
    """Compute step 1 for module 04."""
    return x + y + CONST_04 + 1


def func_04_2(x: int, y: int) -> int:
    """Compute step 2 for module 04."""
    return x + y + CONST_04 + 2


def func_04_3(x: int, y: int) -> int:
    """Compute step 3 for module 04."""
    return x + y + CONST_04 + 3


class Worker_04:
    """A worker class for module 04."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 04."""
        return f"{self.name}-04"

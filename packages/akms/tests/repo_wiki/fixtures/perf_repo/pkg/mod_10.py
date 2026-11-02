"""Module 10 of the perf fixture."""


CONST_10 = 10


def func_10_1(x: int, y: int) -> int:
    """Compute step 1 for module 10."""
    return x + y + CONST_10 + 1


def func_10_2(x: int, y: int) -> int:
    """Compute step 2 for module 10."""
    return x + y + CONST_10 + 2


def func_10_3(x: int, y: int) -> int:
    """Compute step 3 for module 10."""
    return x + y + CONST_10 + 3


class Worker_10:
    """A worker class for module 10."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 10."""
        return f"{self.name}-10"

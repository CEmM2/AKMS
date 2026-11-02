"""Module 45 of the perf fixture."""


CONST_45 = 45


def func_45_1(x: int, y: int) -> int:
    """Compute step 1 for module 45."""
    return x + y + CONST_45 + 1


def func_45_2(x: int, y: int) -> int:
    """Compute step 2 for module 45."""
    return x + y + CONST_45 + 2


def func_45_3(x: int, y: int) -> int:
    """Compute step 3 for module 45."""
    return x + y + CONST_45 + 3


class Worker_45:
    """A worker class for module 45."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 45."""
        return f"{self.name}-45"

"""Module 40 of the perf fixture."""


CONST_40 = 40


def func_40_1(x: int, y: int) -> int:
    """Compute step 1 for module 40."""
    return x + y + CONST_40 + 1


def func_40_2(x: int, y: int) -> int:
    """Compute step 2 for module 40."""
    return x + y + CONST_40 + 2


def func_40_3(x: int, y: int) -> int:
    """Compute step 3 for module 40."""
    return x + y + CONST_40 + 3


class Worker_40:
    """A worker class for module 40."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 40."""
        return f"{self.name}-40"

"""Module 18 of the perf fixture."""


CONST_18 = 18


def func_18_1(x: int, y: int) -> int:
    """Compute step 1 for module 18."""
    return x + y + CONST_18 + 1


def func_18_2(x: int, y: int) -> int:
    """Compute step 2 for module 18."""
    return x + y + CONST_18 + 2


def func_18_3(x: int, y: int) -> int:
    """Compute step 3 for module 18."""
    return x + y + CONST_18 + 3


class Worker_18:
    """A worker class for module 18."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 18."""
        return f"{self.name}-18"

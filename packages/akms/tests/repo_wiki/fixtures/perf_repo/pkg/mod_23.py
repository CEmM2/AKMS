"""Module 23 of the perf fixture."""


CONST_23 = 23


def func_23_1(x: int, y: int) -> int:
    """Compute step 1 for module 23."""
    return x + y + CONST_23 + 1


def func_23_2(x: int, y: int) -> int:
    """Compute step 2 for module 23."""
    return x + y + CONST_23 + 2


def func_23_3(x: int, y: int) -> int:
    """Compute step 3 for module 23."""
    return x + y + CONST_23 + 3


class Worker_23:
    """A worker class for module 23."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 23."""
        return f"{self.name}-23"

"""Module 02 of the perf fixture."""


CONST_02 = 2


def func_02_1(x: int, y: int) -> int:
    """Compute step 1 for module 02."""
    return x + y + CONST_02 + 1


def func_02_2(x: int, y: int) -> int:
    """Compute step 2 for module 02."""
    return x + y + CONST_02 + 2


def func_02_3(x: int, y: int) -> int:
    """Compute step 3 for module 02."""
    return x + y + CONST_02 + 3


class Worker_02:
    """A worker class for module 02."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 02."""
        return f"{self.name}-02"

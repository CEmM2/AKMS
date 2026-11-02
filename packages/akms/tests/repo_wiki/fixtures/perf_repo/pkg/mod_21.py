"""Module 21 of the perf fixture."""


CONST_21 = 21


def func_21_1(x: int, y: int) -> int:
    """Compute step 1 for module 21."""
    return x + y + CONST_21 + 1


def func_21_2(x: int, y: int) -> int:
    """Compute step 2 for module 21."""
    return x + y + CONST_21 + 2


def func_21_3(x: int, y: int) -> int:
    """Compute step 3 for module 21."""
    return x + y + CONST_21 + 3


class Worker_21:
    """A worker class for module 21."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 21."""
        return f"{self.name}-21"

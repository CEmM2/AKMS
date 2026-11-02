"""Module 44 of the perf fixture."""


CONST_44 = 44


def func_44_1(x: int, y: int) -> int:
    """Compute step 1 for module 44."""
    return x + y + CONST_44 + 1


def func_44_2(x: int, y: int) -> int:
    """Compute step 2 for module 44."""
    return x + y + CONST_44 + 2


def func_44_3(x: int, y: int) -> int:
    """Compute step 3 for module 44."""
    return x + y + CONST_44 + 3


class Worker_44:
    """A worker class for module 44."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 44."""
        return f"{self.name}-44"

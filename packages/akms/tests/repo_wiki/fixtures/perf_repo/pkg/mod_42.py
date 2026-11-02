"""Module 42 of the perf fixture."""


CONST_42 = 42


def func_42_1(x: int, y: int) -> int:
    """Compute step 1 for module 42."""
    return x + y + CONST_42 + 1


def func_42_2(x: int, y: int) -> int:
    """Compute step 2 for module 42."""
    return x + y + CONST_42 + 2


def func_42_3(x: int, y: int) -> int:
    """Compute step 3 for module 42."""
    return x + y + CONST_42 + 3


class Worker_42:
    """A worker class for module 42."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 42."""
        return f"{self.name}-42"

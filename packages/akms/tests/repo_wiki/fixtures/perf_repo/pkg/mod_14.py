"""Module 14 of the perf fixture."""


CONST_14 = 14


def func_14_1(x: int, y: int) -> int:
    """Compute step 1 for module 14."""
    return x + y + CONST_14 + 1


def func_14_2(x: int, y: int) -> int:
    """Compute step 2 for module 14."""
    return x + y + CONST_14 + 2


def func_14_3(x: int, y: int) -> int:
    """Compute step 3 for module 14."""
    return x + y + CONST_14 + 3


class Worker_14:
    """A worker class for module 14."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 14."""
        return f"{self.name}-14"

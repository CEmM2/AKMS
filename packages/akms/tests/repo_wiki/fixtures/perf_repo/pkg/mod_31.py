"""Module 31 of the perf fixture."""


CONST_31 = 31


def func_31_1(x: int, y: int) -> int:
    """Compute step 1 for module 31."""
    return x + y + CONST_31 + 1


def func_31_2(x: int, y: int) -> int:
    """Compute step 2 for module 31."""
    return x + y + CONST_31 + 2


def func_31_3(x: int, y: int) -> int:
    """Compute step 3 for module 31."""
    return x + y + CONST_31 + 3


class Worker_31:
    """A worker class for module 31."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 31."""
        return f"{self.name}-31"

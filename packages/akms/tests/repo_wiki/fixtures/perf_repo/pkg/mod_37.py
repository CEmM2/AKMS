"""Module 37 of the perf fixture."""


CONST_37 = 37


def func_37_1(x: int, y: int) -> int:
    """Compute step 1 for module 37."""
    return x + y + CONST_37 + 1


def func_37_2(x: int, y: int) -> int:
    """Compute step 2 for module 37."""
    return x + y + CONST_37 + 2


def func_37_3(x: int, y: int) -> int:
    """Compute step 3 for module 37."""
    return x + y + CONST_37 + 3


class Worker_37:
    """A worker class for module 37."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 37."""
        return f"{self.name}-37"

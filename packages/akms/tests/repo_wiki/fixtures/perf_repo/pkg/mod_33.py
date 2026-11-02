"""Module 33 of the perf fixture."""


CONST_33 = 33


def func_33_1(x: int, y: int) -> int:
    """Compute step 1 for module 33."""
    return x + y + CONST_33 + 1


def func_33_2(x: int, y: int) -> int:
    """Compute step 2 for module 33."""
    return x + y + CONST_33 + 2


def func_33_3(x: int, y: int) -> int:
    """Compute step 3 for module 33."""
    return x + y + CONST_33 + 3


class Worker_33:
    """A worker class for module 33."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 33."""
        return f"{self.name}-33"

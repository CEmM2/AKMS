"""Module 13 of the perf fixture."""


CONST_13 = 13


def func_13_1(x: int, y: int) -> int:
    """Compute step 1 for module 13."""
    return x + y + CONST_13 + 1


def func_13_2(x: int, y: int) -> int:
    """Compute step 2 for module 13."""
    return x + y + CONST_13 + 2


def func_13_3(x: int, y: int) -> int:
    """Compute step 3 for module 13."""
    return x + y + CONST_13 + 3


class Worker_13:
    """A worker class for module 13."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 13."""
        return f"{self.name}-13"

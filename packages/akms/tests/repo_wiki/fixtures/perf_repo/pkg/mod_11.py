"""Module 11 of the perf fixture."""


CONST_11 = 11


def func_11_1(x: int, y: int) -> int:
    """Compute step 1 for module 11."""
    return x + y + CONST_11 + 1


def func_11_2(x: int, y: int) -> int:
    """Compute step 2 for module 11."""
    return x + y + CONST_11 + 2


def func_11_3(x: int, y: int) -> int:
    """Compute step 3 for module 11."""
    return x + y + CONST_11 + 3


class Worker_11:
    """A worker class for module 11."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 11."""
        return f"{self.name}-11"

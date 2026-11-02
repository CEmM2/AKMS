"""Module 28 of the perf fixture."""


CONST_28 = 28


def func_28_1(x: int, y: int) -> int:
    """Compute step 1 for module 28."""
    return x + y + CONST_28 + 1


def func_28_2(x: int, y: int) -> int:
    """Compute step 2 for module 28."""
    return x + y + CONST_28 + 2


def func_28_3(x: int, y: int) -> int:
    """Compute step 3 for module 28."""
    return x + y + CONST_28 + 3


class Worker_28:
    """A worker class for module 28."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 28."""
        return f"{self.name}-28"

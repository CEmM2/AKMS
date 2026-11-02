"""Module 24 of the perf fixture."""


CONST_24 = 24


def func_24_1(x: int, y: int) -> int:
    """Compute step 1 for module 24."""
    return x + y + CONST_24 + 1


def func_24_2(x: int, y: int) -> int:
    """Compute step 2 for module 24."""
    return x + y + CONST_24 + 2


def func_24_3(x: int, y: int) -> int:
    """Compute step 3 for module 24."""
    return x + y + CONST_24 + 3


class Worker_24:
    """A worker class for module 24."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 24."""
        return f"{self.name}-24"

"""Module 29 of the perf fixture."""


CONST_29 = 29


def func_29_1(x: int, y: int) -> int:
    """Compute step 1 for module 29."""
    return x + y + CONST_29 + 1


def func_29_2(x: int, y: int) -> int:
    """Compute step 2 for module 29."""
    return x + y + CONST_29 + 2


def func_29_3(x: int, y: int) -> int:
    """Compute step 3 for module 29."""
    return x + y + CONST_29 + 3


class Worker_29:
    """A worker class for module 29."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 29."""
        return f"{self.name}-29"

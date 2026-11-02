"""Module 41 of the perf fixture."""


CONST_41 = 41


def func_41_1(x: int, y: int) -> int:
    """Compute step 1 for module 41."""
    return x + y + CONST_41 + 1


def func_41_2(x: int, y: int) -> int:
    """Compute step 2 for module 41."""
    return x + y + CONST_41 + 2


def func_41_3(x: int, y: int) -> int:
    """Compute step 3 for module 41."""
    return x + y + CONST_41 + 3


class Worker_41:
    """A worker class for module 41."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 41."""
        return f"{self.name}-41"

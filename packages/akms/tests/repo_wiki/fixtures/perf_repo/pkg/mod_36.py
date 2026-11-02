"""Module 36 of the perf fixture."""


CONST_36 = 36


def func_36_1(x: int, y: int) -> int:
    """Compute step 1 for module 36."""
    return x + y + CONST_36 + 1


def func_36_2(x: int, y: int) -> int:
    """Compute step 2 for module 36."""
    return x + y + CONST_36 + 2


def func_36_3(x: int, y: int) -> int:
    """Compute step 3 for module 36."""
    return x + y + CONST_36 + 3


class Worker_36:
    """A worker class for module 36."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 36."""
        return f"{self.name}-36"

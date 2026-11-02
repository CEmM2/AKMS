"""Module 27 of the perf fixture."""


CONST_27 = 27


def func_27_1(x: int, y: int) -> int:
    """Compute step 1 for module 27."""
    return x + y + CONST_27 + 1


def func_27_2(x: int, y: int) -> int:
    """Compute step 2 for module 27."""
    return x + y + CONST_27 + 2


def func_27_3(x: int, y: int) -> int:
    """Compute step 3 for module 27."""
    return x + y + CONST_27 + 3


class Worker_27:
    """A worker class for module 27."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 27."""
        return f"{self.name}-27"

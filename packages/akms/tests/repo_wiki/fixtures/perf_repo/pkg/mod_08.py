"""Module 08 of the perf fixture."""


CONST_08 = 8


def func_08_1(x: int, y: int) -> int:
    """Compute step 1 for module 08."""
    return x + y + CONST_08 + 1


def func_08_2(x: int, y: int) -> int:
    """Compute step 2 for module 08."""
    return x + y + CONST_08 + 2


def func_08_3(x: int, y: int) -> int:
    """Compute step 3 for module 08."""
    return x + y + CONST_08 + 3


class Worker_08:
    """A worker class for module 08."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 08."""
        return f"{self.name}-08"

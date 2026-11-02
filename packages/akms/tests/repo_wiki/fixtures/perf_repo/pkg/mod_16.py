"""Module 16 of the perf fixture."""


CONST_16 = 16


def func_16_1(x: int, y: int) -> int:
    """Compute step 1 for module 16."""
    return x + y + CONST_16 + 1


def func_16_2(x: int, y: int) -> int:
    """Compute step 2 for module 16."""
    return x + y + CONST_16 + 2


def func_16_3(x: int, y: int) -> int:
    """Compute step 3 for module 16."""
    return x + y + CONST_16 + 3


class Worker_16:
    """A worker class for module 16."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 16."""
        return f"{self.name}-16"

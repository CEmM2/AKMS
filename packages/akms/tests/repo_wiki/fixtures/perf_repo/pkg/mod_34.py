"""Module 34 of the perf fixture."""


CONST_34 = 34


def func_34_1(x: int, y: int) -> int:
    """Compute step 1 for module 34."""
    return x + y + CONST_34 + 1


def func_34_2(x: int, y: int) -> int:
    """Compute step 2 for module 34."""
    return x + y + CONST_34 + 2


def func_34_3(x: int, y: int) -> int:
    """Compute step 3 for module 34."""
    return x + y + CONST_34 + 3


class Worker_34:
    """A worker class for module 34."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 34."""
        return f"{self.name}-34"

"""Module 46 of the perf fixture."""


CONST_46 = 46


def func_46_1(x: int, y: int) -> int:
    """Compute step 1 for module 46."""
    return x + y + CONST_46 + 1


def func_46_2(x: int, y: int) -> int:
    """Compute step 2 for module 46."""
    return x + y + CONST_46 + 2


def func_46_3(x: int, y: int) -> int:
    """Compute step 3 for module 46."""
    return x + y + CONST_46 + 3


class Worker_46:
    """A worker class for module 46."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 46."""
        return f"{self.name}-46"

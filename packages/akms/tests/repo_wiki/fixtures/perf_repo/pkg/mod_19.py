"""Module 19 of the perf fixture."""


CONST_19 = 19


def func_19_1(x: int, y: int) -> int:
    """Compute step 1 for module 19."""
    return x + y + CONST_19 + 1


def func_19_2(x: int, y: int) -> int:
    """Compute step 2 for module 19."""
    return x + y + CONST_19 + 2


def func_19_3(x: int, y: int) -> int:
    """Compute step 3 for module 19."""
    return x + y + CONST_19 + 3


class Worker_19:
    """A worker class for module 19."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 19."""
        return f"{self.name}-19"

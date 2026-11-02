"""Module 47 of the perf fixture."""


CONST_47 = 47


def func_47_1(x: int, y: int) -> int:
    """Compute step 1 for module 47."""
    return x + y + CONST_47 + 1


def func_47_2(x: int, y: int) -> int:
    """Compute step 2 for module 47."""
    return x + y + CONST_47 + 2


def func_47_3(x: int, y: int) -> int:
    """Compute step 3 for module 47."""
    return x + y + CONST_47 + 3


class Worker_47:
    """A worker class for module 47."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 47."""
        return f"{self.name}-47"

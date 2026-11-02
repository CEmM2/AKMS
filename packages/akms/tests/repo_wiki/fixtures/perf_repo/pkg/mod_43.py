"""Module 43 of the perf fixture."""


CONST_43 = 43


def func_43_1(x: int, y: int) -> int:
    """Compute step 1 for module 43."""
    return x + y + CONST_43 + 1


def func_43_2(x: int, y: int) -> int:
    """Compute step 2 for module 43."""
    return x + y + CONST_43 + 2


def func_43_3(x: int, y: int) -> int:
    """Compute step 3 for module 43."""
    return x + y + CONST_43 + 3


class Worker_43:
    """A worker class for module 43."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 43."""
        return f"{self.name}-43"

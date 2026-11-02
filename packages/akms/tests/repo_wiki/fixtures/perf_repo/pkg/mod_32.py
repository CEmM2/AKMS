"""Module 32 of the perf fixture."""


CONST_32 = 32


def func_32_1(x: int, y: int) -> int:
    """Compute step 1 for module 32."""
    return x + y + CONST_32 + 1


def func_32_2(x: int, y: int) -> int:
    """Compute step 2 for module 32."""
    return x + y + CONST_32 + 2


def func_32_3(x: int, y: int) -> int:
    """Compute step 3 for module 32."""
    return x + y + CONST_32 + 3


class Worker_32:
    """A worker class for module 32."""

    def __init__(self, name: str) -> None:
        self.name = name

    def run(self) -> str:
        """Run worker 32."""
        return f"{self.name}-32"

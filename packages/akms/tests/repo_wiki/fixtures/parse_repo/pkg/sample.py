"""Parser fixture."""

import os
from pathlib import Path

CONSTANT: int = 7


def decorated(fn):
    return fn


class Base:
    pass


class Child(Base):
    """Child docs."""

    @decorated
    async def run(self, path: Path) -> str:
        """Run docs."""

        def nested(value: str) -> str:
            return value.upper()

        return nested(os.fspath(path))

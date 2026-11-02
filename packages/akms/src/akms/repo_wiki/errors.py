"""Error types and build error helpers."""

from __future__ import annotations

from dataclasses import asdict, dataclass


class RepoWikiError(Exception):
    """Base exception for expected repo-wiki failures."""


@dataclass(slots=True)
class BuildError:
    path: str
    stage: str
    message: str
    line: int | None = None
    column: int | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, object]) -> "BuildError":
        line_value = data.get("line")
        column_value = data.get("column")
        return cls(
            path=str(data.get("path", "")),
            stage=str(data.get("stage", "")),
            message=str(data.get("message", "")),
            line=line_value if isinstance(line_value, int) else None,
            column=column_value if isinstance(column_value, int) else None,
        )

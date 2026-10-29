"""Parse and order failure-memory lesson IDs.

Legacy IDs are ``L`` plus decimal digits and sort as ``(0, number)``.
Dated IDs are ``L<YYYYMMDD>-<4 crockford>`` and sort as
``(1, date, suffix)``. Every legacy ID sorts before every dated ID.
"""

from __future__ import annotations

import re

from akms_failure_memory.errors import FailureMemoryError


CROCKFORD_ALPHABET = "0123456789abcdefghjkmnpqrstvwxyz"
DATED_ID_ATTEMPTS = 32
_LEGACY_ID = re.compile(r"L[0-9]+")
_DATED_ID = re.compile(r"L([0-9]{8})-([0-9a-hjkmnp-tv-z]{4})")
SUFFIX_RE = re.compile(r"[0-9a-hjkmnp-tv-z]{4}")
ALLOCATION_DATE_RE = re.compile(r"[0-9]{8}")


def lesson_id_sort_key(lesson_id: str) -> tuple[int, int] | tuple[int, str, str]:
    """Return the shared order key for a legacy or dated lesson ID."""
    if isinstance(lesson_id, str) and _LEGACY_ID.fullmatch(lesson_id):
        return (0, int(lesson_id[1:]))
    if isinstance(lesson_id, str):
        dated = _DATED_ID.fullmatch(lesson_id)
        if dated is not None:
            return (1, dated.group(1), dated.group(2))
    raise FailureMemoryError(
        f"Unrecognized lesson ID {lesson_id!r}",
        code="registry_id",
    )


def legacy_lesson_number(lesson_id: str) -> int:
    """Return the decimal value of a legacy ID. Dated IDs are an error."""
    key = lesson_id_sort_key(lesson_id)
    number = key[1]
    if not isinstance(number, int):
        raise FailureMemoryError(
            f"Sequential allocation cannot use dated lesson ID {lesson_id!r}",
            code="registry_id",
        )
    return number

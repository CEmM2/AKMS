"""Dependency-free YAML subset (nested mappings, scalars, scalar lists); not a general parser."""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence


def dump_yaml(data: Mapping[str, object], indent: int = 0) -> str:
    lines: list[str] = []
    pad = " " * indent
    for key in sorted(data):
        value = data[key]
        if isinstance(value, Mapping):
            lines.append(f"{pad}{key}:")
            lines.append(dump_yaml(value, indent + 2).rstrip())
        elif isinstance(value, list):
            lines.append(f"{pad}{key}:")
            for item in value:
                if isinstance(item, Mapping):
                    lines.append(f"{pad}  -")
                    lines.append(dump_yaml(item, indent + 4).rstrip())
                else:
                    lines.append(f"{pad}  - {format_scalar(item)}")
        else:
            lines.append(f"{pad}{key}: {format_scalar(value)}")
    return "\n".join(lines) + "\n"


def format_scalar(value: object) -> str:
    if value is None:
        return "null"
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return str(value)
    text = str(value)
    if text == "" or any(ch in text for ch in ":#[]{}&*!|>'\"%@`"):
        return json.dumps(text)
    return text


def load_yaml(text: str) -> dict[str, object]:
    lines = [
        raw.rstrip()
        for raw in text.splitlines()
        if raw.strip() and not raw.lstrip().startswith("#")
    ]
    root: dict[str, object] = {}
    stack: list[tuple[int, object]] = [(-1, root)]
    for idx, raw in enumerate(lines):
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        while stack and indent <= stack[-1][0]:
            stack.pop()
        parent = stack[-1][1]
        if line.startswith("- "):
            if not isinstance(parent, list):
                raise ValueError("list item without list parent")
            parent.append(parse_scalar(line[2:].strip()))
            continue
        key, sep, value = line.partition(":")
        if not sep:
            raise ValueError(f"invalid config line: {raw}")
        key = key.strip()
        value = value.strip()
        if not isinstance(parent, dict):
            raise ValueError("mapping item without mapping parent")
        if value:
            parent[key] = parse_scalar(value)
            continue
        next_is_list = _next_more_indented_list(lines, idx)
        container: object = [] if next_is_list else {}
        parent[key] = container
        stack.append((indent, container))
    return root


def _next_more_indented_list(lines: Sequence[str], idx: int) -> bool:
    current = lines[idx]
    current_indent = len(current) - len(current.lstrip(" "))
    for raw in lines[idx + 1 :]:
        indent = len(raw) - len(raw.lstrip(" "))
        if indent <= current_indent:
            return False
        return raw.strip().startswith("- ")
    return False


def parse_scalar(value: str) -> object:
    if value in {"null", "None", "~"}:
        return None
    if value == "true":
        return True
    if value == "false":
        return False
    if value.startswith('"'):
        return json.loads(value)
    if value.startswith("'"):
        if not value.endswith("'"):
            raise ValueError(f"unterminated single-quoted scalar: {value}")
        return value[1:-1].replace("''", "'")
    try:
        return int(value)
    except ValueError:
        return value

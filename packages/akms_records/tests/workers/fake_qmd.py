"""A stand-in for the qmd command, for tests that must not need the real one.

Keeps every document's text in the database file, and keeps the text of documents
that go away, as the real tool does until a cleanup. Vectors are word overlap.
"""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path


def main(arguments: list[str]) -> int:
    log = os.environ.get("FAKE_QMD_LOG")
    if log:
        with open(log, "a", encoding="utf-8") as handle:
            handle.write(
                json.dumps({"argv": arguments, "env": dict(os.environ)}) + "\n"
            )
    failing = os.environ.get("FAKE_QMD_FAIL")
    if failing and arguments[0] == failing:
        print("simulated failure", file=sys.stderr)
        return 3
    database = Path(os.environ["INDEX_PATH"])
    state = (
        json.loads(database.read_text(encoding="utf-8"))
        if database.exists()
        else {"docs": "", "active": {}, "retained": []}
    )
    if arguments[:2] == ["collection", "add"]:
        state["docs"] = arguments[2]
    if arguments[0] in {"collection", "update"}:
        state["active"] = {}
        for path in sorted(Path(state["docs"]).glob("*.md")):
            text = path.read_text(encoding="utf-8")
            state["active"][path.name] = text
            state["retained"].append(text)
        database.write_text(json.dumps(state), encoding="utf-8")
        return 0
    if arguments[0] == "embed":
        return 0
    if arguments[0] == "query":
        if os.environ.get("FAKE_QMD_NOT_JSON"):
            print("not json")
            return 0
        words = set(re.findall(r"\w+", arguments[1].lower())) - {"vec"}
        limit = int(arguments[arguments.index("-n") + 1])

        def overlap(text: str) -> int:
            return len(words & set(re.findall(r"\w+", text.lower())))

        ranked = sorted(
            state["active"], key=lambda n: (-overlap(state["active"][n]), n)
        )
        print(json.dumps([{"file": f"qmd://records/{n}"} for n in ranked[:limit]]))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

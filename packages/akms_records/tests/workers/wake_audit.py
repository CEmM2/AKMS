"""Run ``wake`` under an audit hook and report every file it opened.

Run as ``<python> wake_audit.py REPO HOME AGENT``. Imports of AKMS or
failure-memory packages are blocked, and the opened paths go to stdout as JSON
with the wake's Markdown, so the test can prove what wake reads.
"""

from __future__ import annotations

import json
import os
import sys


class Blocker:
    def find_spec(self, name, path=None, target=None):
        if name.split(".")[0] in ("akms", "akms_failure_memory"):
            raise ImportError(f"{name} is blocked in this test")
        return None


def main() -> int:
    repo, home, agent = sys.argv[1:4]
    os.environ["AKMS_RECORDS_HOME"] = home
    opened: list[str] = []

    def hook(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            opened.append(os.fsdecode(args[0]))
        elif event == "sqlite3.connect" and args:
            opened.append(os.fsdecode(args[0]))

    sys.meta_path.insert(0, Blocker())
    from akms_records import wake

    sys.addaudithook(hook)
    result = wake(
        agent=agent,
        task="failure lesson mesh",
        budget_tokens=4000,
        scopes=["project:example"],
        repo=repo,
        include_imported=True,
        include_promoted=True,
    )
    print(
        json.dumps(
            {
                "opened": opened,
                "markdown": result.render_markdown(),
                "used": result.used_tokens,
                "included": [entry.record_id for entry in result.entries],
            }
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""A fake external summarizer for the consolidation tests.

Run as ``<python> summarizer.py MODE``: reads the consolidation input as JSON
on stdin and writes a reply on stdout. Bytes, not text streams, so the
behaviour is the same on Windows.

Modes: ``ok`` (one paraphrase per source, each citing it), ``uncited`` (an
assertion without a source), ``badjson``, ``exit`` (status 3) and ``sleep``.
"""

from __future__ import annotations

import json
import sys
import time


def main() -> int:
    mode = sys.argv[1]
    data = json.loads(sys.stdin.buffer.read().decode("utf-8"))
    if mode == "sleep":
        time.sleep(60)
    if mode == "exit":
        sys.stderr.write("summarizer failed on purpose\n")
        return 3
    if mode == "badjson":
        sys.stdout.buffer.write(b"{not json")
        return 0
    if mode == "uncited":
        assertions = [{"text": "A claim without a source", "sources": []}]
    else:
        assertions = [
            {"text": "In short: " + source["summary"], "sources": [source["ref"]]}
            for source in data["sources"]
        ]
    reply = {
        "assertions": assertions,
        "provider": {"name": "fake-summarizer", "version": "1.0"},
    }
    sys.stdout.buffer.write(json.dumps(reply).encode("utf-8"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Public smoke test: ``repo-wiki`` works from a plain ``akms`` install.

The repository wiki and code-mirror exporter ship inside ``akms``, so the core
wheel alone, with no extras, must provide a ``repo-wiki`` that exports AKMS
mirrors. Rust, C++ (tree-sitter) and Julia need ``akms[multilang]``; Python
does not.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

BIN = Path(sys.executable).parent


def test_repo_wiki_exports_a_python_mirror(tmp_path: Path) -> None:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "value.py").write_text(
        '"""A value."""\n\nVALUE = 1\n', encoding="utf-8"
    )

    result = subprocess.run(
        [
            str(BIN / "repo-wiki"),
            "--repo-root",
            str(tmp_path),
            "export-akms",
            "--output",
            "akms-output",
            "--phase",
            "1",
            "--generated-at",
            "2026-01-01T00:00:00+00:00",
            "--full",
            "--json",
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    payload = json.loads(result.stdout)
    assert payload["errors"] == []
    [written] = payload["written"]
    assert written["source_path"] == "pkg/value.py"
    assert (tmp_path / "akms-output" / written["generated_path"]).is_file()

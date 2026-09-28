#!/usr/bin/env python3
"""Install `akms` with every extra combination from freshly built wheels.

`akms[learn]`, `akms[all]` and friends are only useful if each one installs
exactly the companion packages it promises, those packages resolve together,
and their commands run. This builds nothing itself: point it at a directory
holding one wheel per package in the family, as `uv build` writes them.

Sibling packages are forced to the local wheels through uv overrides, which
apply only when a package is actually required. So a case that should not pull
`akms-learn` still does not, while one that does gets this tree's build rather
than whatever PyPI holds at the same version.

Usage: python scripts/check_extras_matrix.py <wheelhouse> [--python 3.12]
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import subprocess
import sys
import tempfile
from pathlib import Path

SIBLINGS = (
    "akms-learn",
    "akms-failure-memory",
    "akms-nodes-gen",
    "compmech-reference-pack",
)

# Extra -> sibling distributions it must install, and commands they provide.
EXTRAS = {
    "learn": ({"akms-learn"}, ["akms-learn"]),
    "failure-memory": ({"akms-failure-memory"}, ["failure-memory"]),
    "nodes-gen": ({"akms-nodes-gen"}, ["akms-pick"]),
    "compmech": ({"akms-learn", "compmech-reference-pack"}, ["akms-learn"]),
}

CASES = [
    "",
    "learn",
    "failure-memory",
    "nodes-gen",
    "compmech",
    "learn,failure-memory",
    "learn,nodes-gen",
    "failure-memory,nodes-gen",
    "all",
]

CORE_COMMANDS = ["akms", "akms-mcp-stdio"]

PROBE = """
import importlib.metadata as m, json
names = {d.metadata["Name"].lower().replace("_", "-") for d in m.distributions()}
plugins = sorted(e.name for e in m.entry_points(group="akms.plugins"))
print(json.dumps({"names": sorted(names), "plugins": plugins}))
"""


def wheel_for(wheelhouse: Path, distribution: str) -> Path:
    stem = distribution.replace("-", "_")
    matches = sorted(wheelhouse.glob(f"{stem}-*.whl"))
    if len(matches) != 1:
        raise SystemExit(
            f"expected one {distribution} wheel in {wheelhouse}: {matches}"
        )
    return matches[0].resolve()


def expected_for(case: str) -> tuple[set[str], list[str]]:
    extras = [e for e in case.split(",") if e]
    if extras == ["all"]:
        extras = list(EXTRAS)
    siblings: set[str] = set()
    commands = list(CORE_COMMANDS)
    for extra in extras:
        dists, cmds = EXTRAS[extra]
        siblings |= dists
        commands += cmds
    return siblings, commands


def run(cmd: list[str], **kwargs) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, **kwargs)


def check_case(
    case: str, core: Path, overrides: Path, python: str, root: Path
) -> list[str]:
    label = f"akms[{case}]" if case else "akms"
    venv = root / (case.replace(",", "+") or "core")
    errors: list[str] = []
    made = run(["uv", "venv", "-q", str(venv), "--python", python])
    if made.returncode:
        return [f"{label}: venv failed: {made.stderr.strip()}"]
    exe = venv / ("Scripts" if sys.platform == "win32" else "bin")
    requirement = (
        f"akms[{case}] @ {core.as_uri()}" if case else f"akms @ {core.as_uri()}"
    )
    installed = run(
        [
            "uv",
            "pip",
            "install",
            "-q",
            "--python",
            str(exe / "python"),
            "--override",
            str(overrides),
            requirement,
        ]
    )
    if installed.returncode:
        return [f"{label}: install failed:\n{installed.stderr.strip()}"]

    checked = run(["uv", "pip", "check", "--python", str(exe / "python")])
    if checked.returncode:
        errors.append(
            f"{label}: dependency check failed:\n{checked.stdout}{checked.stderr}"
        )

    probe = json.loads(run([str(exe / "python"), "-c", PROBE]).stdout)
    present = {name for name in probe["names"] if name in SIBLINGS}
    siblings, commands = expected_for(case)
    if present != siblings:
        errors.append(
            f"{label}: installed siblings {sorted(present)}, expected {sorted(siblings)}"
        )
    if ("akms-learn" in siblings) != ("learn" in probe["plugins"]):
        errors.append(f"{label}: akms.plugins entry points are {probe['plugins']}")

    for command in commands:
        try:
            result = run([str(exe / command), "--help"], timeout=60)
        except FileNotFoundError:
            errors.append(f"{label}: command {command} is not installed")
            continue
        if result.returncode:
            errors.append(f"{label}: {command} --help exited {result.returncode}")

    print(
        f"{'FAIL' if errors else 'ok  '} {label}: {', '.join(sorted(present)) or 'core only'}"
    )
    return errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("wheelhouse", type=Path)
    parser.add_argument("--python", default="3.12")
    args = parser.parse_args()

    if importlib.util.find_spec("tomllib") is None:  # pragma: no cover
        raise SystemExit("Python 3.11+ required")

    core = wheel_for(args.wheelhouse, "akms")
    with tempfile.TemporaryDirectory(prefix="akms-extras-") as tmp:
        root = Path(tmp)
        overrides = root / "overrides.txt"
        overrides.write_text(
            "".join(
                f"{name} @ {wheel_for(args.wheelhouse, name).as_uri()}\n"
                for name in SIBLINGS
            ),
            encoding="utf-8",
        )
        errors: list[str] = []
        for case in CASES:
            errors += check_case(case, core, overrides, args.python, root)

    if errors:
        print("\nExtras matrix failed:", file=sys.stderr)
        for error in errors:
            print(f"  - {error}", file=sys.stderr)
        return 1
    print(f"Extras matrix passed: {len(CASES)} combinations.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

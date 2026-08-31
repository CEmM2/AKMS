from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _expand(p: str | os.PathLike[str]) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(str(p))))


@dataclass(frozen=True)
class Paths:
    repo_root: Path
    plan_md: Path
    bbt_json: Path
    zotsums_root: Path
    state_file: Path
    queries_file: Path
    inputs_dir: Path
    sources_dir: Path

    @classmethod
    def resolve(cls) -> "Paths":
        # Default: repo root is two levels above this file's package
        # (.../Packages/AKMS_nodes_gen/src/akms_nodes_gen/batch_picker/config.py)
        here = Path(__file__).resolve()
        default_repo = here.parents[5]
        repo_root = _expand(os.environ.get("AKMS_REPO_ROOT", default_repo))

        plan_md = _expand(
            os.environ.get(
                "AKMS_PLAN_MD",
                repo_root / "Packages" / "AKMS_nodes_gen" / "generation_plan.md",
            )
        )
        # There is no portable location for a Zotero/BetterBibTeX export, so
        # the default is a neutral placeholder: set AKMS_ZOTSUMS_ROOT (or
        # AKMS_BBT_JSON) to wherever yours actually lives.
        zotsums_root = _expand(
            os.environ.get("AKMS_ZOTSUMS_ROOT", "~/ZotSums")
        )
        bbt_json = _expand(
            os.environ.get("AKMS_BBT_JSON", zotsums_root / "zsumbib.json")
        )
        state_file = _expand(
            os.environ.get(
                "AKMS_BATCH_STATE",
                repo_root / "Sources_Evals" / "NLM" / "batch_assignments.json",
            )
        )
        queries_file = _expand(
            os.environ.get(
                "AKMS_SAVED_QUERIES",
                repo_root / "Sources_Evals" / "NLM" / "saved_queries.json",
            )
        )
        inputs_dir = _expand(
            os.environ.get(
                "AKMS_NLM_INPUTS",
                repo_root / "Sources_Evals" / "NLM" / "Inputs",
            )
        )
        sources_dir = _expand(
            os.environ.get(
                "AKMS_SOURCES_NEW",
                repo_root / "AKMS_Sources" / "new",
            )
        )
        return cls(
            repo_root=repo_root,
            plan_md=plan_md,
            bbt_json=bbt_json,
            zotsums_root=zotsums_root,
            state_file=state_file,
            queries_file=queries_file,
            inputs_dir=inputs_dir,
            sources_dir=sources_dir,
        )

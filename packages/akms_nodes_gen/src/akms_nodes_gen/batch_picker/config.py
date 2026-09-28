"""Where the batch picker reads its inputs and keeps its state.

Every path is resolved in the same order: an explicit command-line value, then
its environment variable, then a default. The defaults assume nothing about the
layout of an AKMS checkout, so an installed `akms-pick` works from any
directory:

- the plan is ``./generation_plan.md``;
- state, saved queries, exported plan JSON and staged PDFs live in a workspace,
  which defaults to the directory holding the plan;
- the Zotero export and per-paper summaries default to the zsum locations
  (``~/ZotSums``), and both are optional at start-up.

Setting ``AKMS_REPO_ROOT`` restores the monorepo layout, in which the plan sits
in the node-generation package and state lives under ``Sources_Evals/NLM``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

ZSUM_URL = "https://github.com/CEmM2/zotero-summarizer"
DOCS_URL = "https://cemm2.github.io/AKMS/reference/nodes-gen/batch-picker/"


def _expand(p: str | os.PathLike[str]) -> Path:
    return Path(os.path.expanduser(os.path.expandvars(str(p))))


def _pick(explicit: str | os.PathLike[str] | None, env: str, default: Path) -> Path:
    if explicit is not None:
        return _expand(explicit)
    value = os.environ.get(env)
    return _expand(value) if value else default


@dataclass(frozen=True)
class Paths:
    workspace: Path
    plan_md: Path
    bbt_json: Path
    zotsums_root: Path
    state_file: Path
    queries_file: Path
    inputs_dir: Path
    sources_dir: Path

    @classmethod
    def resolve(
        cls,
        *,
        plan: str | os.PathLike[str] | None = None,
        bibtex_json: str | os.PathLike[str] | None = None,
        zsum_root: str | os.PathLike[str] | None = None,
        workspace: str | os.PathLike[str] | None = None,
    ) -> "Paths":
        legacy_root = os.environ.get("AKMS_REPO_ROOT")
        if legacy_root:
            root = _expand(legacy_root)
            plan_md = _pick(
                plan,
                "AKMS_PLAN_MD",
                root / "Packages" / "AKMS_nodes_gen" / "generation_plan.md",
            )
            ws = _pick(workspace, "AKMS_PICKER_WORKSPACE", root)
            nlm = root / "Sources_Evals" / "NLM"
            state_default = nlm / "batch_assignments.json"
            queries_default = nlm / "saved_queries.json"
            inputs_default = nlm / "Inputs"
            sources_default = root / "AKMS_Sources" / "new"
            if workspace is not None or os.environ.get("AKMS_PICKER_WORKSPACE"):
                state_default = ws / "batch_assignments.json"
                queries_default = ws / "saved_queries.json"
                inputs_default = ws / "plans"
                sources_default = ws / "pdfs"
        else:
            plan_md = _pick(plan, "AKMS_PLAN_MD", Path.cwd() / "generation_plan.md")
            ws = _pick(workspace, "AKMS_PICKER_WORKSPACE", plan_md.parent)
            state_default = ws / "batch_assignments.json"
            queries_default = ws / "saved_queries.json"
            inputs_default = ws / "plans"
            sources_default = ws / "pdfs"

        zotsums_root = _pick(zsum_root, "AKMS_ZOTSUMS_ROOT", _expand("~/ZotSums"))
        bbt_json = _pick(bibtex_json, "AKMS_BBT_JSON", zotsums_root / "zsumbib.json")
        return cls(
            workspace=ws,
            plan_md=plan_md,
            bbt_json=bbt_json,
            zotsums_root=zotsums_root,
            state_file=_expand(os.environ.get("AKMS_BATCH_STATE") or state_default),
            queries_file=_expand(
                os.environ.get("AKMS_SAVED_QUERIES") or queries_default
            ),
            inputs_dir=_expand(os.environ.get("AKMS_NLM_INPUTS") or inputs_default),
            sources_dir=_expand(os.environ.get("AKMS_SOURCES_NEW") or sources_default),
        )

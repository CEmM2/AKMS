"""Side-effecting actions: write per-batch plan JSON, stage PDFs into the
batch source folder, drive the `nlm` CLI to create a notebook + upload sources.
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .loaders import Catalog, Paper
from .plan_parser import Batch
from .state import BatchAssignment


@dataclass
class ActionResult:
    ok: bool
    message: str
    data: dict[str, Any]


def _now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _short_label(paper: Paper) -> str:
    """Human label like 'Goswami et al. (2020) — Adaptive fourth-order ...'"""
    if not paper.authors:
        head = paper.citekey
    elif len(paper.authors) == 1:
        head = paper.authors[0].split(",")[0]
    else:
        head = paper.authors[0].split(",")[0] + " et al."
    year = f" ({paper.year})" if paper.year else ""
    title = paper.title.strip()
    if len(title) > 90:
        title = title[:87].rstrip() + "..."
    return f"{head}{year} — {title}" if title else f"{head}{year}"


def write_plan_json(
    batch: Batch,
    assignment: BatchAssignment,
    catalog: Catalog,
    inputs_dir: Path,
) -> Path:
    """Write a node-gen-invoker plan JSON for a single batch."""
    inputs_dir.mkdir(parents=True, exist_ok=True)
    out_path = inputs_dir / f"{batch.pdf_slug or batch.id}_plan.json"

    notebook_sources = [
        _short_label(catalog.papers[ck])
        for ck in assignment.papers
        if ck in catalog.papers
    ]
    payload = {
        "plan": f"Round {batch.round} — {batch.round_title}",
        "batch_id": batch.id,
        "batch_title": batch.title,
        "round": batch.round,
        "subdomain": batch.round_subdomain,
        "total_nodes": len(batch.nodes),
        "new_nodes": len(batch.nodes),
        "existing_nodes": 0,
        "notes": {
            "source_convention": "Sources picked manually via batch_picker UI; one NLM notebook per batch.",
            "notebook_setup": (
                f"Upload {len(notebook_sources)} PDFs from AKMS_Sources/new/{batch.pdf_slug or batch.id}/"
            ),
            "round": batch.round,
        },
        "notebook_sources": notebook_sources,
        "papers_by_citekey": [
            {
                "citekey": ck,
                "label": _short_label(catalog.papers[ck]),
                "pdf": catalog.papers[ck].pdf_path,
                "has_pdf": catalog.papers[ck].has_pdf,
            }
            for ck in assignment.papers
            if ck in catalog.papers
        ],
        "clusters": [
            {
                "cluster": batch.id,
                "name": batch.title,
                "notebook_sources": notebook_sources,
                "nodes": [
                    {
                        "id": n.node_id,
                        "title": n.title,
                        "size": n.size,
                        "status": "new",
                    }
                    for n in batch.nodes
                ],
            }
        ],
        "nlm": {
            "notebook_id": assignment.nlm_notebook_id,
            "notebook_url": assignment.nlm_notebook_url,
            "uploaded_papers": list(assignment.uploaded_papers),
        },
        "generated_at": _now_iso(),
    }
    out_path.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return out_path


def stage_pdfs(
    batch: Batch,
    assignment: BatchAssignment,
    catalog: Catalog,
    sources_dir: Path,
    use_symlink: bool = True,
) -> ActionResult:
    """Drop PDFs into AKMS_Sources/new/<slug>/ as symlinks (or copies)."""
    folder_name = batch.pdf_slug or batch.id
    target = sources_dir / folder_name
    target.mkdir(parents=True, exist_ok=True)

    staged: list[str] = []
    skipped: list[dict[str, str]] = []

    for ck in assignment.papers:
        paper = catalog.papers.get(ck)
        if not paper or not paper.has_pdf:
            skipped.append({"citekey": ck, "reason": "no local PDF"})
            continue
        src = Path(paper.pdf_path)
        if not src.exists():
            skipped.append({"citekey": ck, "reason": f"missing on disk: {src}"})
            continue
        # Filename: <citekey>.pdf — stable, dedupable
        dst = target / f"{ck}.pdf"
        if dst.exists() or dst.is_symlink():
            try:
                dst.unlink()
            except OSError:
                pass
        try:
            if use_symlink:
                os.symlink(src, dst)
            else:
                shutil.copy2(src, dst)
            staged.append(ck)
        except OSError as e:
            skipped.append({"citekey": ck, "reason": str(e)})

    return ActionResult(
        ok=True,
        message=f"Staged {len(staged)} PDFs into {target}",
        data={
            "target_dir": str(target),
            "staged": staged,
            "skipped": skipped,
            "use_symlink": use_symlink,
        },
    )


def _run_nlm(
    args: list[str], timeout: float = 600.0
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["nlm", *args],
        capture_output=True,
        text=True,
        timeout=timeout,
        check=False,
    )


def _extract_id_from_output(text: str) -> str:
    """`nlm notebook create` prints the notebook ID — try a few formats."""
    import re

    # JSON line like {"id": "..."}
    m = re.search(r'"(?:notebook_)?id"\s*:\s*"([^"]+)"', text)
    if m:
        return m.group(1)
    # Naked id token line: "Created notebook: nb_abc"
    m = re.search(r"\b(nb_[A-Za-z0-9_-]+)\b", text)
    if m:
        return m.group(1)
    # Long opaque id (Drive-style)
    m = re.search(r"\b([A-Za-z0-9_-]{20,})\b", text)
    if m:
        return m.group(1)
    return ""


def create_notebook_and_upload(
    batch: Batch,
    assignment: BatchAssignment,
    catalog: Catalog,
    sources_dir: Path,
    upload: bool = True,
    wait: bool = False,
) -> ActionResult:
    """Run `nlm notebook create` and (optionally) upload all PDFs.

    The notebook ID is captured into the assignment for durability. If the
    notebook already exists on the assignment, we reuse it and only upload
    the missing PDFs.
    """
    # Reuse if already created
    nb_id = assignment.nlm_notebook_id
    log: list[str] = []

    title = f"AKMS {batch.id} — {batch.title}"

    if not nb_id:
        cp = _run_nlm(["notebook", "create", title])
        log.append(f"$ nlm notebook create '{title}'")
        log.append(cp.stdout.strip())
        if cp.stderr.strip():
            log.append("[stderr] " + cp.stderr.strip())
        if cp.returncode != 0:
            return ActionResult(
                ok=False,
                message=f"`nlm notebook create` exited {cp.returncode}",
                data={"log": "\n".join(log)},
            )
        nb_id = _extract_id_from_output(cp.stdout)
        if not nb_id:
            return ActionResult(
                ok=False,
                message="Could not parse notebook ID from `nlm` output. Inspect log.",
                data={"log": "\n".join(log)},
            )
        assignment.nlm_notebook_id = nb_id

    if not upload:
        return ActionResult(
            ok=True,
            message=f"Notebook ready (id={nb_id}); upload skipped.",
            data={"notebook_id": nb_id, "log": "\n".join(log)},
        )

    # Upload PDFs that haven't been uploaded yet
    folder_name = batch.pdf_slug or batch.id
    pdf_dir = sources_dir / folder_name

    uploaded_now: list[str] = []
    failures: list[dict[str, str]] = []

    pending = [ck for ck in assignment.papers if ck not in assignment.uploaded_papers]

    for ck in pending:
        paper = catalog.papers.get(ck)
        if not paper or not paper.has_pdf:
            failures.append({"citekey": ck, "reason": "no PDF"})
            continue
        # Prefer staged path inside the batch dir; fall back to original.
        staged = pdf_dir / f"{ck}.pdf"
        pdf_path = str(staged if staged.exists() else paper.pdf_path)

        cmd = [
            "source",
            "add",
            nb_id,
            "--file",
            pdf_path,
            "--title",
            _short_label(paper),
        ]
        if wait:
            cmd.append("--wait")

        cp = _run_nlm(cmd, timeout=900.0)
        log.append(f"$ nlm {' '.join(cmd)}")
        log.append(cp.stdout.strip())
        if cp.stderr.strip():
            log.append("[stderr] " + cp.stderr.strip())
        if cp.returncode != 0:
            failures.append(
                {
                    "citekey": ck,
                    "reason": f"nlm exited {cp.returncode}: {cp.stderr.strip()[:200]}",
                }
            )
            continue
        uploaded_now.append(ck)
        assignment.uploaded_papers.append(ck)

    return ActionResult(
        ok=not failures,
        message=(
            f"Uploaded {len(uploaded_now)} of {len(pending)} pending PDFs"
            + (f" ({len(failures)} failed)" if failures else "")
        ),
        data={
            "notebook_id": nb_id,
            "uploaded": uploaded_now,
            "failures": failures,
            "log": "\n".join(log),
        },
    )

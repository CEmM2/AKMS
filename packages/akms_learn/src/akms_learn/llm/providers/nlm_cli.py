"""Grounded nlm-CLI provider.

A *grounded* :class:`~akms_learn.llm.protocol.LLMProvider` that fills learning
drops/outcomes by querying a NotebookLM notebook whose sources are the active
nodes (+ optional PDF files), via the **nlm CLI** — deterministic, scriptable,
and lower-token than the notebooklm MCP (which this adapter deliberately does
**not** use).

Grounding is source-locked *by construction*: the notebook's sources are the
supplied nodes, so the model can only ground in them, and the emitted sections
cite exactly ``active_node_ids``.

Division of labour
------------------
Populating the notebook from nodes (+ PDFs) is the **host's existing AKMS
NotebookLM workflow** (Logic-Loom ``/api/nlm/*`` / ``akms_nodes_gen``); this
adapter *queries* the already-populated notebook. The grounding bundle is passed
via the Protocol's ``sources`` argument (a dict):

    sources = {
        "notebook_id": "<nlm notebook id>",   # required to ground
        "profile":     "<nlm auth profile>",  # optional
        "pdf_paths":   ["/path/a.pdf", ...],  # optional, informational
        "timeout":     120,                    # optional seconds
    }

Without a ``notebook_id`` there is nothing to ground against, so the adapter
returns ``[]`` (graceful) and the ``llm_expanded`` mode falls back to the
deterministic packet.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from typing import TYPE_CHECKING

from akms_learn.llm.registry import register
from akms_learn.models.llm_expansion import (
    GeneratedSection,
    compute_content_hash,
)

if TYPE_CHECKING:
    from akms_learn.llm.protocol import ProviderSources
    from akms_learn.models.llm_expansion import LLMExpansionPolicy

__all__ = ["NLM_PROVIDER_NAME", "nlm_available", "nlm_grounded"]

#: Registry name + provenance ``generator`` id.
NLM_PROVIDER_NAME = "nlm"
_NLM_MODEL = "notebooklm"
_DEFAULT_TIMEOUT = 120


def nlm_available() -> bool:
    """Return ``True`` when the ``nlm`` CLI is on PATH (used by the capability gate)."""
    return shutil.which("nlm") is not None


def _run_nlm_cli(args: list[str], *, timeout: int) -> str:
    """Run ``nlm <args>`` and return stdout. Module-level so tests can patch it.

    CLI only — never the notebooklm MCP.
    """
    try:
        completed = subprocess.run(
            ["nlm", *args],
            check=False,
            capture_output=True,
            text=True,
            # Wall-clock guard 30s beyond the CLI's own ``--timeout`` so a CLI
            # that respects ``--timeout`` exits first; the buffer only fires if
            # the CLI hangs past its own deadline.
            timeout=timeout + 30,
        )
    except subprocess.TimeoutExpired as exc:  # pragma: no cover - timing path
        raise RuntimeError(f"nlm CLI timed out after {timeout}s") from exc
    except FileNotFoundError as exc:
        raise RuntimeError(
            "nlm CLI binary not found on PATH — install nlm and ensure it is on PATH."
        ) from exc
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"nlm CLI failed (rc={completed.returncode}): {detail}")
    return completed.stdout


def _extract_answer(raw: str) -> str:
    """Pull the answer text out of ``nlm … --json`` output, tolerant of shape."""
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return raw.strip()
    if isinstance(data, dict):
        for key in ("answer", "text", "content", "response"):
            value = data.get(key)
            if isinstance(value, str) and value:
                return value
    return raw.strip()


def nlm_grounded(
    topic: str,
    active_node_ids: tuple[str, ...] | list[str],
    policy: LLMExpansionPolicy | None = None,
    *,
    sources: ProviderSources | None = None,
) -> list[GeneratedSection]:
    """Fill one grounded section by querying the configured NotebookLM notebook.

    Returns ``[]`` (graceful) when there is no ``notebook_id`` in ``sources`` or
    no active node ids — nothing to ground against.
    """
    bundle = sources or {}
    notebook_id = bundle.get("notebook_id")
    valid_ids = tuple(str(nid) for nid in active_node_ids if nid)
    if not notebook_id or not valid_ids:
        return []

    profile = bundle.get("profile")
    timeout = int(bundle.get("timeout", _DEFAULT_TIMEOUT))

    # Add any optional PDF files as notebook sources before querying, so the
    # grounding context includes them. The active *nodes* are populated by the
    # host's existing AKMS NotebookLM workflow; here we top up the PDFs the
    # caller passed through the grounding bundle.
    pdf_paths = bundle.get("pdf_paths") or ()
    if isinstance(pdf_paths, str):  # tolerate a single path passed unwrapped
        pdf_paths = [pdf_paths]
    for pdf_path in pdf_paths:
        add_args = ["source", "add", str(notebook_id), str(pdf_path)]
        if profile:
            add_args += ["--profile", str(profile)]
        _run_nlm_cli(add_args, timeout=timeout)

    question = (
        f"Using only this notebook's sources, write one concise learning outcome "
        f"for the topic {topic!r}, grounded in the nodes "
        f"{', '.join(valid_ids)}. Introduce no claim absent from the sources."
    )
    args = [
        "notebook",
        "query",
        str(notebook_id),
        question,
        "--json",
        "--timeout",
        str(timeout),
    ]
    if profile:
        args += ["--profile", str(profile)]

    content = _extract_answer(_run_nlm_cli(args, timeout=timeout))

    section_id = f"{valid_ids[0]}::nlm-outcome"
    return [
        GeneratedSection(
            id=section_id,
            generator=NLM_PROVIDER_NAME,
            model=_NLM_MODEL,
            source_node_ids=valid_ids,
            validation_status="valid",
            content_hash=compute_content_hash(
                section_id=section_id,
                source_node_ids=valid_ids,
                content=content,
            ),
            content=content,
        )
    ]


def register_nlm_provider() -> None:
    """Register the nlm provider iff the nlm CLI is on PATH.

    Conditional so that on a host without the ``nlm`` CLI the provider is **not**
    registered — ``resolve("nlm")`` then raises ``PreconditionError``, a clear
    "unavailable" signal for callers. A *configured notebook* is still required
    at call time (handled inside ``nlm_grounded``).
    """
    if nlm_available():
        register(NLM_PROVIDER_NAME, nlm_grounded)


register_nlm_provider()

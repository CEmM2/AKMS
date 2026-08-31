"""Assessment exporter for Learning Source Packets (assessment_first mode).

Exporter Protocol conformance
-----------------------------
This module exposes a top-level :func:`export` function matching the
``Exporter`` callable protocol declared in :mod:`akms_learn.exporters`:

.. code-block:: python

    def export(
        packet: LearningSourcePacket,
        output_dir: Path,
        /,
    ) -> list[Path]: ...

The compiler dispatches this function from Stage 9 of
:func:`akms_learn.compiler.compile_learning_source` when ``"assessment"``
appears in ``request.exporters``.  Callers MUST NOT invoke this module's
functions directly — use
:func:`~akms_learn.compiler.compile_learning_source` with
``exporters=["assessment"]`` instead.

Design invariants — public / hidden separation (closure-gate)
-------------------------------------------------------------
* **Field allowlist, not blacklist.** The public renderers (``assessment.md``
  and ``assessment.json``) emit *only* the fields enumerated in
  :data:`_PUBLIC_FIELDS`.  Any new field on
  :class:`~akms_learn.models.AssessmentItem` (or any extra key carried via
  AssessmentView's ``extra="allow"``) is silently dropped from the public
  surface unless explicitly added to the allowlist.  This is a deliberate
  defense against hidden-answer leakage: a blacklist of
  ``{"hidden_answer"}`` would silently leak any future answer-bearing field.
* **rubric.md is a separate file.**  The hidden answer key is written to a
  third file (``rubric.md``).  It never appears in ``assessment.md`` or
  ``assessment.json``.
* **Independent disablement.**  Dispatch is name-based: if ``"assessment"``
  is absent from ``request.exporters``, this module is never imported.  When
  invoked with an LSP that carries no assessment items, the exporter still
  emits ``assessment.md``/``assessment.json`` (empty) and a header-only
  ``rubric.md`` — never raises.
* **Capability-gated.**  Requires the ``html`` extra
  (``jinja2``) via ``require_capability("quiz_export")``; missing the extra
  raises :class:`~akms_learn.capability_gates.PreconditionError`.  This is
  nominal — the exporter has no third-party runtime dependency — but matches
  the other exporters' pattern so the capability surface stays uniform.
* **Pure** — no network, no LLM, no global state mutations.
* **Deterministic** — identical inputs produce byte-equal output for all
  three files.  Items are sorted by ``item_id``; JSON is rendered with
  ``sort_keys=True`` and ``indent=2``.

File layout
-----------
``assessment.md``
    Public Markdown listing of every item.  Each item rendered as a
    section: ``## <item_id>`` heading, then ``kind``, ``target_node_ids``,
    and the public ``prompt``.  Nothing from :data:`_HIDDEN_FIELDS`.

``assessment.json``
    Public JSON mirror — one object per item, fields restricted to
    :data:`_PUBLIC_FIELDS`.  Top-level keys: ``items``, ``packet_id``,
    ``compiler_version``, ``schema``.

``rubric.md``
    Hidden answer key, keyed by ``item_id``, sorted lexicographically.
    Only items whose ``hidden_answer`` is a non-empty string are emitted.
    When no item carries a ``hidden_answer``, the file contains only a
    header noting "no rubric items".
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from akms_learn.capability_gates import require_capability

if TYPE_CHECKING:
    from akms_learn.models import LearningSourcePacket

__all__ = ["export", "_PUBLIC_FIELDS", "_HIDDEN_FIELDS"]


# ---------------------------------------------------------------------------
# Field allowlist — the ONLY fields that may appear in public output.
# ---------------------------------------------------------------------------
#
# allowlist (NOT a blacklist).  A new AssessmentItem field MUST be added here
# explicitly before it can appear in assessment.md or assessment.json — this
# is the closure-gate invariant against hidden-answer leakage.
_PUBLIC_FIELDS: tuple[str, ...] = (
    "item_id",
    "kind",
    "prompt",
    "target_node_ids",
)

#: Field names that MUST NEVER appear in public output.  This set is used by
#: defensive assertions only; the real guarantee comes from
#: :data:`_PUBLIC_FIELDS` being an allowlist.
_HIDDEN_FIELDS: frozenset[str] = frozenset({"hidden_answer"})


# ---------------------------------------------------------------------------
# Item normalisation
# ---------------------------------------------------------------------------


def _coerce_item(raw: Any) -> dict[str, Any]:
    """Coerce one assessment entry to a plain dict.

    ``packet.body.assessments`` holds :class:`AssessmentView` instances with
    ``extra="allow"``; the assessment_first mode dumps
    :class:`AssessmentItem` records into that slot.  This helper handles
    both forms (Pydantic model instance and plain dict) without importing
    AssessmentView/AssessmentItem (one-way import discipline + avoids
    circular import via models package).
    """
    if hasattr(raw, "model_dump"):
        return dict(raw.model_dump())
    if isinstance(raw, dict):
        return dict(raw)
    # Defensive: unknown shape — return empty dict so this entry is skipped.
    return {}


def _normalise_item_id(item: dict[str, Any]) -> str:
    """Read the item id from an item dict.

    AssessmentItem uses ``id`` as its field name; we re-key to ``item_id``
    on the public surface (a) to match the spec wording ("keyed by item_id")
    and (b) so a bare ``id`` does not get confused with JSON document ids.
    Accepts both ``item_id`` and ``id`` on the input side for forward compat.
    """
    raw_id = item.get("item_id")
    if raw_id is None:
        raw_id = item.get("id")
    return str(raw_id) if raw_id is not None else ""


def _public_view(item: dict[str, Any]) -> dict[str, Any]:
    """Project *item* through the allowlist.

    The returned dict carries ONLY keys from :data:`_PUBLIC_FIELDS`.  Values
    are coerced to deterministic types: tuples become sorted lists, strings
    stay as strings, missing fields are emitted with a deterministic empty
    value (``""`` for strings, ``[]`` for lists) so the JSON shape is stable
    across items.
    """
    item_id = _normalise_item_id(item)
    kind = item.get("kind")
    prompt = item.get("prompt")
    targets = item.get("target_node_ids") or ()
    if isinstance(targets, (list, tuple)):
        target_list = sorted(str(t) for t in targets)
    else:
        target_list = []
    return {
        "item_id": item_id,
        "kind": str(kind) if kind is not None else "",
        "prompt": str(prompt) if prompt is not None else "",
        "target_node_ids": target_list,
    }


def _hidden_answer_for(item: dict[str, Any]) -> str | None:
    """Return the trimmed ``hidden_answer`` or ``None`` when absent/empty."""
    answer = item.get("hidden_answer")
    if answer is None:
        return None
    if not isinstance(answer, str):
        answer = str(answer)
    stripped = answer.strip()
    return stripped if stripped else None


# ---------------------------------------------------------------------------
# Renderers
# ---------------------------------------------------------------------------


def _render_assessment_md(
    public_items: list[dict[str, Any]],
    packet_id: str,
) -> str:
    """Render the public ``assessment.md`` body.

    Items are emitted in lexicographic order of ``item_id``.  When the LSP
    carries no items, an explanatory placeholder line is written so the
    file is never silently empty.
    """
    lines: list[str] = []
    lines.append(f"# Assessment — {packet_id}")
    lines.append("")
    if not public_items:
        lines.append("_no assessment items in this packet_")
        lines.append("")
        return "\n".join(lines)
    for item in public_items:
        lines.append(f"## {item['item_id']}")
        lines.append("")
        lines.append(f"- **kind:** {item['kind']}")
        lines.append(
            "- **target_node_ids:** " + (", ".join(item["target_node_ids"]) or "_none_")
        )
        lines.append("")
        lines.append("**Prompt:**")
        lines.append("")
        lines.append(item["prompt"])
        lines.append("")
    return "\n".join(lines)


def _render_assessment_json(
    public_items: list[dict[str, Any]],
    packet: "LearningSourcePacket",
) -> str:
    """Render the public ``assessment.json`` body.

    Top-level keys are ``items``, ``packet_id``, ``compiler_version``, and
    ``schema``.  ``json.dumps`` is called with ``sort_keys=True`` and
    ``indent=2`` so two runs against the same LSP produce byte-equal output.
    """
    document = {
        "schema": "akms-learn/assessment/v1",
        "packet_id": str(packet.packet_id),
        "compiler_version": str(getattr(packet.compiler, "version", "") or ""),
        "items": public_items,
    }
    return json.dumps(
        document,
        sort_keys=True,
        indent=2,
        ensure_ascii=False,
    )


def _render_rubric_md(
    items_by_id: list[tuple[str, str]],
    packet_id: str,
) -> str:
    """Render the hidden answer key.

    *items_by_id* is a list of ``(item_id, hidden_answer)`` pairs already
    filtered to entries with a non-empty answer.  Sorted lexicographically
    by ``item_id``.  When the list is empty, the file contains a header
    plus an explanatory line ("no rubric items in this packet").
    """
    lines: list[str] = []
    lines.append(f"# Rubric (hidden answer key) — {packet_id}")
    lines.append("")
    if not items_by_id:
        lines.append("_no rubric items in this packet_")
        lines.append("")
        return "\n".join(lines)
    for item_id, answer in items_by_id:
        lines.append(f"## {item_id}")
        lines.append("")
        lines.append(answer)
        lines.append("")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Exporter Protocol entry point
# ---------------------------------------------------------------------------


def export(
    packet: "LearningSourcePacket",
    output_dir: Path,
    /,
) -> list[Path]:
    """Write ``assessment.md``, ``assessment.json``, and ``rubric.md``.

    This function is the Exporter Protocol entry point; the compiler's
    Stage 9 dispatches it automatically when ``"assessment"`` appears in
    ``request.exporters``.

    Public / hidden separation
    --------------------------
    The two public files (``assessment.md``, ``assessment.json``) are
    rendered through the :data:`_PUBLIC_FIELDS` allowlist — any field not on
    the allowlist (including ``hidden_answer``) is dropped before
    serialisation.  The hidden answer key is written to ``rubric.md`` only.

    Parameters
    ----------
    packet:
        The fully-validated :class:`~akms_learn.models.LearningSourcePacket`
        produced by :func:`~akms_learn.compiler.compile_learning_source`.
        The exporter reads assessment items from ``packet.body.assessments``.
    output_dir:
        Target directory.  Created on demand if it does not exist.

    Returns
    -------
    list[Path]
        Three absolute paths in deterministic order:
        ``assessment.md`` → ``assessment.json`` → ``rubric.md``.

    Raises
    ------
    PreconditionError
        When the ``html`` extra (``jinja2``) is not installed.
    """
    # ------------------------------------------------------------------
    # Capability gate — first operation (nominal: this exporter has no
    # third-party runtime dependency, but the gate keeps the capability
    # surface uniform with the other exporters).
    # ------------------------------------------------------------------
    require_capability("quiz_export")

    # ------------------------------------------------------------------
    # Collect items.  Sort by item_id for determinism.
    # ------------------------------------------------------------------
    raw_items = list(getattr(packet.body, "assessments", None) or [])
    items: list[dict[str, Any]] = [d for d in (_coerce_item(r) for r in raw_items) if d]
    items.sort(key=_normalise_item_id)

    # Public surface — allowlist projection.
    public_items: list[dict[str, Any]] = [_public_view(it) for it in items]

    # Defensive sanity check: the allowlist must not contain any hidden
    # field.  This is a constant-time assertion; failure indicates someone
    # edited _PUBLIC_FIELDS to include a hidden key by mistake.
    assert not (set(_PUBLIC_FIELDS) & _HIDDEN_FIELDS), (
        "_PUBLIC_FIELDS includes a hidden field — closure-gate violation"
    )

    # Hidden surface — sorted (item_id, hidden_answer) pairs.
    rubric_pairs: list[tuple[str, str]] = []
    for it in items:
        item_id = _normalise_item_id(it)
        if not item_id:
            continue
        answer = _hidden_answer_for(it)
        if answer is None:
            continue
        rubric_pairs.append((item_id, answer))
    rubric_pairs.sort(key=lambda p: p[0])

    # ------------------------------------------------------------------
    # Write files.
    # ------------------------------------------------------------------
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    packet_id = str(packet.packet_id)

    md_path = out_dir / "assessment.md"
    md_path.write_text(
        _render_assessment_md(public_items, packet_id),
        encoding="utf-8",
    )

    json_path = out_dir / "assessment.json"
    json_path.write_text(
        _render_assessment_json(public_items, packet),
        encoding="utf-8",
    )

    rubric_path = out_dir / "rubric.md"
    rubric_path.write_text(
        _render_rubric_md(rubric_pairs, packet_id),
        encoding="utf-8",
    )

    return [md_path, json_path, rubric_path]

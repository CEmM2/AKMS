"""Learning request input model + deterministic normalization and hashing.

This module implements the request contract: the 11
normalized fields of a learning request, their default values, the canonical
form used for hashing, and the SHA-256 hash function that downstream code
embeds into :class:`LearningRequestInfo` (see ``models.py``).

The 11 normalized fields (plan §10, L189-L201) — exact set, no more, no less:

==================  ==============  ==================================
Field               Type            Default
==================  ==============  ==================================
topic               str             (required)
goal                str             (required)
audience            str             ``"engineer"``
depth               str             ``"implementation"``
generation_option   str             (required)
seed_tags           list[str]       ``[]``
max_nodes           int | None      ``None``
max_depth           int | None      ``None``
include_pitfalls    bool            ``True``
include_code_links  bool            ``True``
exporters           list[str]       ``[]``
==================  ==============  ==================================

Normalization rules (plan §10, L203 + Phase 2 context L17):

* Extra keys (e.g. Logic-Loom UI state: ``preview_mode``, ``ui_theme``,
  ``session_id``) are silently dropped — they MUST NOT contribute to the hash.
* ``topic`` and ``goal`` are ``.strip()``-trimmed but **case-preserving**.
* ``audience``, ``depth``, ``generation_option`` are trimmed then lowercased
  (they are enum-like).
* ``seed_tags`` elements are stripped + lowercased + sorted.
* ``exporters`` elements are stripped + lowercased + sorted (enum-like names
  such as ``markdown`` / ``bundle``).
* Lists are sorted before serialization so hash is order-invariant.

Hashing (plan §10, L203):

* ``request_hash`` is the SHA-256 hex digest of the canonical JSON form,
  produced with ``json.dumps(..., sort_keys=True,
  separators=(",", ":"), ensure_ascii=False)`` encoded as UTF-8.
* The combination of ``sort_keys=True`` and the fixed 11-field projection
  makes the hash byte-identical across Python sessions and platforms.
* ``ensure_ascii=False`` is mandatory so non-ASCII topics (e.g. ``"j² return
  mapping"``) hash consistently regardless of locale.

Spec refs: the akms-learn internal specification (not published),
the akms-learn internal specification (not published).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from akms_learn.models.learner_profile import LearnerProfile

__all__ = [
    "NORMALIZED_FIELDS",
    "LearnerProfile",
    "LearningRequest",
    "normalize_request",
    "request_hash",
    "to_canonical_dict",
]


# Exact, ordered list of the 11 normalized fields (plan §10, L189-L201).
NORMALIZED_FIELDS: tuple[str, ...] = (
    "topic",
    "goal",
    "audience",
    "depth",
    "generation_option",
    "seed_tags",
    "max_nodes",
    "max_depth",
    "include_pitfalls",
    "include_code_links",
    "exporters",
)


class LearningRequest(BaseModel):
    """Input model for a learning request (plan §10).

    Only these 11 fields contribute to ``request_hash``. UI-only state from
    Logic-Loom (preview_mode, ui_theme, session_id, ...) is rejected at
    ``normalize_request`` time and never reaches the hash.

    ``audience``, ``depth``, ``generation_option`` are kept as free-form
    ``str`` rather than ``Literal`` to avoid coupling Phase 2 to a frozen
    enum set; ``normalize_request`` lowercases them so case variations
    collapse to a single canonical form.
    """

    model_config = ConfigDict(extra="ignore")

    topic: str
    goal: str
    audience: str = "engineer"
    depth: str = "implementation"
    generation_option: str
    seed_tags: list[str] = Field(default_factory=list)
    max_nodes: int | None = None
    max_depth: int | None = None
    include_pitfalls: bool = True
    include_code_links: bool = True
    exporters: list[str] = Field(default_factory=list)
    # ``required_capabilities`` is INTENTIONALLY excluded from
    # :data:`NORMALIZED_FIELDS` (and therefore from ``request_hash``). It
    # signals additional plugin features the caller demands, not a change to
    # the conceptual learning request — two requests that differ only in
    # required_capabilities address the same topic/goal and must hash
    # identically. The compiler's Stage 1 ``_check_required_capabilities``
    # enforces availability and raises :class:`LearningCapabilityError`
    # when any entry is missing.
    required_capabilities: list[str] = Field(default_factory=list)
    # ``policy`` is INTENTIONALLY excluded from :data:`NORMALIZED_FIELDS` (and
    # therefore from ``request_hash``). It selects per-mode rendering options
    # (currently used by ``implementation_first`` mode) and does
    # NOT change the conceptual learning request. Two requests that differ
    # only in policy address the same topic/goal and must hash identically.
    # Values: ``"code_first"`` | ``"concept_first"``. ``None`` is normalised
    # to ``"concept_first"`` by mode callers.
    policy: str | None = None
    #   # ``granularity`` is INTENTIONALLY excluded from :data:`NORMALIZED_FIELDS`
    #       # (and therefore from ``request_hash``). It selects per-mode rendering
    #       # variants (currently used by ``multi_granularity`` mode) and does NOT
    #       # change the conceptual learning request. Two requests that differ only in
    #       # granularity address the same topic/goal and must hash identically.
    #       # Values: ``"overview"`` | ``"standard"`` | ``"deep_dive"``. ``None`` means
    #       # "no explicit selection — fall back to convention-based detection in the
    #       # multi_granularity mode, defaulting to 'standard' if no signal is found".
    #       # This field never enters the AKMS v2 graph — it lives on the request, the
    #       # LSP request block, and the mode result only.
    granularity: Literal["overview", "standard", "deep_dive"] | None = None
    # ``rich_html`` is INTENTIONALLY excluded from :data:`NORMALIZED_FIELDS`
    # (and therefore from ``request_hash``). It only toggles the html exporter
    # between the default offline self-contained preview and a rich MathJax +
    # rendered-algorithm page; it does not change node selection, so two requests
    # differing only in ``rich_html`` must hash identically.
    rich_html: bool = False
    # ``learner_profile`` is INTENTIONALLY excluded from :data:`NORMALIZED_FIELDS`
    # (and therefore from ``request_hash``). It carries personalisation hints
    # (knows/weak/goals/conservative_mode) used exclusively by the
    # ``adaptive_path`` compiler mode. Two requests that differ
    # only in ``learner_profile`` address the same topic/goal and must hash
    # identically. The profile lives on the request, the LSP adaptive summary,
    # and provenance only — it never enters the AKMS v2 graph schema.
    learner_profile: LearnerProfile | None = None

    # ------------------------------------------------------------------ #
    # LLM expansion fields                                               #
    # ------------------------------------------------------------------ #
    # These four fields are INTENTIONALLY excluded from :data:`NORMALIZED_FIELDS`
    # (and therefore from ``request_hash``).  They are passthrough config for the
    # ``llm_expanded`` compiler mode; two requests that differ only in LLM
    # settings address the same topic/goal and must hash identically.
    #
    # ``llm_enable``   — master switch; ``False`` disables LLM expansion entirely.
    # ``llm_provider`` — registry name of the provider to invoke (``akms`` |
    #                    ``nlm`` | ``no_provider_stub``).  The default is
    #                    ``"no_provider_stub"`` so callers that set
    #                    ``llm_enable=True`` without specifying a provider still
    #                    exercise the deterministic stub path.
    # ``llm_policy``   — optional expansion policy override; ``None`` defers to
    #                    the node-level hint and falls back to ``"source_locked"``.
    #                    Must be one of the :data:`~akms_learn.models.llm_expansion.LLM_EXPANSION_POLICIES`
    #                    literals when set.
    # ``sources``      — optional grounded-context bundle forwarded to the
    #                    provider; carries ``notebook_id``, ``pdf_paths``,
    #                    ``profile`` etc. for grounded providers.  ``None`` for
    #                    ungrounded providers, which ignore it.
    #
    # The mapping llm_enable→enable_llm / llm_provider→provider /
    # llm_policy→policy / sources→sources is centralised in
    # ``compiler._build_llm_expansion_request`` (the single adapter) so the two
    # models never drift.
    llm_enable: bool = False
    llm_provider: str = "no_provider_stub"
    llm_policy: str | None = None
    sources: dict[str, Any] | None = None


# Defaults — must match the LearningRequest field defaults above. Kept as a
# module-level constant so ``normalize_request`` can apply them to a raw dict
# without instantiating LearningRequest (which would also work, but is more
# permissive on the input side).
_DEFAULTS: dict[str, Any] = {
    "audience": "engineer",
    "depth": "implementation",
    "seed_tags": [],
    "max_nodes": None,
    "max_depth": None,
    "include_pitfalls": True,
    "include_code_links": True,
    "exporters": [],
}


def _norm_str_trim(value: Any) -> str:
    """Trim whitespace; preserve case."""
    if value is None:
        return ""
    return str(value).strip()


def _norm_enum_str(value: Any, default: str) -> str:
    """Trim + lowercase enum-like string fields. Falls back to default."""
    if value is None:
        return default
    s = str(value).strip().lower()
    return s if s else default


def _norm_str_list(value: Any) -> list[str]:
    """Trim + lowercase each element, drop empties, sort for order-invariance."""
    if value is None:
        return []
    if not isinstance(value, (list, tuple)):
        raise TypeError(
            f"expected list/tuple for list-valued request field, got {type(value).__name__}"
        )
    cleaned = [str(x).strip().lower() for x in value]
    cleaned = [x for x in cleaned if x]
    return sorted(cleaned)


def _coerce_optional_int(value: Any) -> int | None:
    if value is None:
        return None
    return int(value)


def _coerce_bool(value: Any, default: bool) -> bool:
    if value is None:
        return default
    return bool(value)


def normalize_request(raw: dict[str, Any] | LearningRequest) -> dict[str, Any]:
    """Return the canonical dict representation of a learning request.

    The output is a plain ``dict`` containing exactly the 11 normalized
    fields (see :data:`NORMALIZED_FIELDS`), with extras dropped and lists
    sorted. Calling :func:`request_hash` on the result yields a byte-stable
    SHA-256 digest (plan §10, L203).

    Behavior:

    * Accepts either a raw ``dict`` (e.g. from JSON / Logic-Loom UI) or a
      validated :class:`LearningRequest` instance.
    * Drops keys not in the 11-field schema — including Logic-Loom UI state
      such as ``preview_mode``, ``ui_theme``, ``session_id``.
    * ``topic``/``goal`` are ``.strip()`` only (case preserved).
    * ``audience``/``depth``/``generation_option`` are trimmed + lowercased.
    * ``seed_tags``/``exporters`` elements are trimmed + lowercased + sorted.
    * Missing optional fields receive documented defaults.
    """
    if isinstance(raw, LearningRequest):
        raw_dict: dict[str, Any] = raw.model_dump()
    elif isinstance(raw, dict):
        raw_dict = raw
    else:
        raise TypeError(
            f"normalize_request expects dict or LearningRequest, got {type(raw).__name__}"
        )

    # Pull only the 11 known fields. Anything else is dropped.
    canonical: dict[str, Any] = {
        "topic": _norm_str_trim(raw_dict.get("topic", "")),
        "goal": _norm_str_trim(raw_dict.get("goal", "")),
        "audience": _norm_enum_str(raw_dict.get("audience"), _DEFAULTS["audience"]),
        "depth": _norm_enum_str(raw_dict.get("depth"), _DEFAULTS["depth"]),
        "generation_option": _norm_enum_str(raw_dict.get("generation_option"), ""),
        "seed_tags": _norm_str_list(raw_dict.get("seed_tags")),
        "max_nodes": _coerce_optional_int(raw_dict.get("max_nodes")),
        "max_depth": _coerce_optional_int(raw_dict.get("max_depth")),
        "include_pitfalls": _coerce_bool(
            raw_dict.get("include_pitfalls"), _DEFAULTS["include_pitfalls"]
        ),
        "include_code_links": _coerce_bool(
            raw_dict.get("include_code_links"), _DEFAULTS["include_code_links"]
        ),
        "exporters": _norm_str_list(raw_dict.get("exporters")),
    }
    return canonical


def to_canonical_dict(req: LearningRequest | dict[str, Any]) -> dict[str, Any]:
    """Convenience alias for :func:`normalize_request`.

    Provided so call-sites that read more naturally as "give me the canonical
    dict for this request" don't have to import ``normalize_request``
    directly. Returns the same canonical form (same 11 keys, same rules).
    """
    return normalize_request(req)


def request_hash(normalized: dict[str, Any]) -> str:
    """Return the 64-char hex SHA-256 digest of the canonical JSON form.

    The input is expected to be the output of :func:`normalize_request`
    (or an equivalently shaped dict). The function is idempotent for
    pre-normalized input and byte-identical across Python sessions because:

    * ``sort_keys=True`` makes the JSON form key-order-invariant.
    * ``separators=(",", ":")`` removes incidental whitespace.
    * ``ensure_ascii=False`` keeps non-ASCII characters in their native
      UTF-8 form so the digest does not depend on locale or escape choice.

    See :func:`normalize_request` for the canonical key set and rules.
    """
    payload = json.dumps(
        normalized,
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()

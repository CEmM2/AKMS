"""Mode: llm_expanded — source-locked LLM expansion after LSP validation.

Produces a Learning Source Packet view that **optionally** carries LLM-
generated explanatory prose under ``generated_sections``.  The deterministic
LSP is captured **before** any LLM call and is the authoritative
byte-identical baseline returned when LLM expansion is disabled or
unavailable.

Design decisions
----------------
* **Deterministic-first, LLM-second** — the first action of
  :func:`llm_expanded_mode` is to build the deterministic packet shape and
  freeze a deep copy under ``pre_expansion_packet``.  This is the artefact
  the byte-identical contract is asserted against.  The deterministic
  shape is derived from the authoritative :func:`order_nodes` output —
  same primitive every other structured mode receives.
* **Default-off LLM** — :class:`LLMExpansionRequest.enable_llm` defaults
  to ``False``.  Disabling LLM is therefore the path-of-least-effort and
  must produce a byte-identical packet vs. the deterministic baseline.
* **Deterministic default provider** — the built-in
  :func:`~akms_learn.llm.no_provider_stub.no_provider_stub` is always
  available; it never imports an optional package; and it never
  performs a network call.  Real providers resolve from the provider
  registry and opt into ``require_capability("llm_expanded")``.
* **Capability gate is provider-conditional** — the built-in stub is
  exempt from the gate (it is the default and is always available).  When
  the caller asks for a non-stub provider, :func:`require_capability` runs
  on entry; absent ``llm`` extra raises :class:`PreconditionError` before
  any work begins.  This matches the Phase 1 contract: ``llm`` is an
  intentionally empty extra and the no-provider path remains usable
  without it.
* **Source-locked citations are a HARD invariant** — every
  GeneratedSection a provider returns runs through
  :func:`_validate_citations` before being attached.  Sections that cite
  any node id not in ``packet.nodes`` are NEVER attached to the final
  LSP; a single ``llm_citation_outside_packet`` warning per rejected
  section is emitted instead.  The mode has no bypass branch — the same
  validator runs for the stub provider AND any future external provider.
* **Policy enforcement** — ``source_locked`` is the conservative default
  and is enforced implicitly: the stub paraphrases without introducing
  new claims, and the citation validator rejects any orphan claim.
  ``explanatory_only`` and ``no_new_claims`` are accepted policy values
  whose stricter heuristic checks are TBD; for the no-provider stub all
  three policies behave identically because the stub never invents
  claims.
* **Deterministic ordering** — the surviving GeneratedSections are sorted
  by ``(source_node_ids[0], id)`` so two consecutive runs with the same
  stub output produce byte-identical ``generated_sections`` lists.
* **Pure function** — :func:`llm_expanded_mode` never mutates
  ``graph_slice``, ``ordered_nodes``, or ``request``.  The frozen
  ``pre_expansion_packet`` deep-copy is preserved verbatim on the result.
* **No execution at compile time** — no ``subprocess``, ``exec``, ``eval``,
  ``%run``, or ``nbclient`` calls anywhere in this module.

Warning codes
-------------
``llm_citation_outside_packet``
    Emitted once per rejected GeneratedSection whose ``source_node_ids``
    include any id absent from ``packet.nodes``.  ``source_ref`` carries
    the section id so warnings dedup naturally per section.
``llm_provider_unavailable``
    Emitted when the caller requests a provider that is not registered
    in the provider registry.  The mode falls back to the deterministic
    packet in this case rather than crashing — the byte-identical
    baseline contract still holds.
"""

from __future__ import annotations

import copy
from typing import Any

from pydantic import BaseModel, ConfigDict

from akms_learn.capability_gates import PreconditionError, require_capability
from akms_learn.graph_import import GraphSlice
from akms_learn.llm.no_provider_stub import NO_PROVIDER_STUB_GENERATOR
from akms_learn.llm.registry import resolve, resolve_default_provider
from akms_learn.models import LearningWarning
from akms_learn.models.llm_expansion import (
    LLM_EXPANSION_POLICIES,
    GeneratedSection,
    LLMExpansionPolicy,
    build_llm_provenance,
)
from akms_learn.optional_metadata import read_v21_metadata
from akms_learn.requests import LearningRequest
from akms_learn.warnings import WarningAccumulator

__all__ = [
    "LLMExpandedResult",
    "LLMExpansionRequest",
    "llm_expanded_mode",
]


# ---------------------------------------------------------------------------
# Request-side model (lightweight; opt-in switch + provider selector)
# ---------------------------------------------------------------------------


class LLMExpansionRequest(BaseModel):
    """Per-call configuration for the ``llm_expanded`` mode.

    Fields
    ------
    enable_llm:
        Master switch.  Defaults to ``False`` so the byte-identical
        contract is the path of least effort — callers must
        explicitly opt in to LLM expansion.
    provider:
        Name of the LLM provider to invoke when ``enable_llm`` is
        ``True``.  Providers resolve from the provider registry (the
        built-in ``"no_provider_stub"`` plus registered adapters such as
        ``"akms"`` and ``"nlm"``).  An UNREGISTERED provider name degrades
        to the deterministic packet with an ``llm_provider_unavailable``
        warning.
    policy:
        Optional explicit expansion policy.  Overrides any per-node
        ``expansion_policy`` v2.1 hint.  ``None`` defers to the node-level
        hint and falls back to ``"source_locked"`` when no hint exists.
    topic_override:
        Optional override for the topic string passed to the provider.
        When ``None`` the mode reads ``request.topic`` directly.  Useful
        primarily for tests that want to vary the topic without
        rebuilding a :class:`LearningRequest`.
    sources:
        Optional grounded-context bundle threaded to the provider's
        ``sources`` argument.  Carries ``notebook_id``, ``pdf_paths``,
        ``profile`` etc. for grounded providers (e.g. ``nlm``); ``None``
        for ungrounded providers, which ignore it.
    """

    model_config = ConfigDict(frozen=True)

    enable_llm: bool = False
    provider: str = NO_PROVIDER_STUB_GENERATOR
    policy: LLMExpansionPolicy | None = None
    topic_override: str | None = None
    sources: dict[str, Any] | None = None


# ---------------------------------------------------------------------------
# Result type
# ---------------------------------------------------------------------------


class LLMExpandedResult:
    """Structured result from :func:`llm_expanded_mode`.

    Attributes
    ----------
    packet:
        The final compiled packet payload (a plain dict).  When LLM
        expansion is disabled or unavailable, this is byte-identical to
        ``pre_expansion_packet``.  When expansion ran successfully, the
        packet additionally carries a ``generated_sections`` key (a list
        of GeneratedSection dicts) AND a ``llm_provenance`` block under
        ``packet["provenance"]["llm"]``.
    pre_expansion_packet:
        Frozen deep copy of the deterministic packet captured BEFORE any
        provider call.  Two consecutive calls with the same inputs
        produce equal ``pre_expansion_packet`` dicts down to the byte
        level (after canonical JSON serialisation).
    generated_sections:
        List of GeneratedSection models attached to the final packet,
        sorted by ``(source_node_ids[0], id)``.  Empty when LLM expansion
        was disabled, the provider returned nothing, or every section was
        rejected by the citation validator.
    policy:
        The effective :class:`~akms_learn.models.LLMExpansionPolicy`
        applied during compilation.  ``None`` when LLM expansion was
        disabled (so no policy ever ran).
    warnings:
        List of :class:`~akms_learn.models.LearningWarning` instances
        emitted during compilation.  Contains one entry per rejected
        GeneratedSection (``llm_citation_outside_packet``) and one entry
        per unavailable-provider fallback (``llm_provider_unavailable``).
    """

    __slots__ = (
        "generated_sections",
        "packet",
        "policy",
        "pre_expansion_packet",
        "warnings",
    )

    def __init__(
        self,
        packet: dict[str, Any],
        pre_expansion_packet: dict[str, Any],
        generated_sections: list[GeneratedSection],
        policy: LLMExpansionPolicy | None,
        warnings: list[LearningWarning],
    ) -> None:
        self.packet = packet
        self.pre_expansion_packet = pre_expansion_packet
        self.generated_sections = generated_sections
        self.policy = policy
        self.warnings = warnings


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _build_deterministic_packet(
    graph_slice: GraphSlice,
    ordered_nodes: list[str],
) -> dict[str, Any]:
    """Build the deterministic packet payload (the byte-identical baseline).

    The payload is a plain ``dict`` — never a Pydantic model — because the
    byte-identical contract is asserted via canonical JSON serialisation
    and dicts are easier to round-trip than models.  Every collection is
    sorted; no timestamps appear anywhere.

    Shape::

        {
            "nodes":         {node_id: node_dict_copy, ...},   # sorted keys
            "node_ids":      [node_id, ...],                   # sorted list
            "reading_order": [node_id, ...],                   # input order,
                                                               #   filtered
            "edge_ids":      [edge_id, ...],                   # sorted list
        }
    """
    nodes_by_id: dict[str, dict[str, Any]] = {}
    for raw in graph_slice.nodes:
        nid = raw.get("node_id")
        if nid is not None:
            nodes_by_id[str(nid)] = dict(raw)

    sorted_node_ids = sorted(nodes_by_id.keys())
    reading_order = [nid for nid in ordered_nodes if nid in nodes_by_id]
    edge_ids = sorted(str(e.get("edge_id")) for e in graph_slice.edges if e.get("edge_id"))

    return {
        # Materialise nodes as a key-sorted dict so JSON-canonical dumps
        # yield byte-identical output across runs.
        "nodes": {nid: dict(nodes_by_id[nid]) for nid in sorted_node_ids},
        "node_ids": sorted_node_ids,
        "reading_order": reading_order,
        "edge_ids": edge_ids,
    }


def _resolve_policy(
    explicit: LLMExpansionPolicy | None,
    nodes_by_id: dict[str, dict[str, Any]],
    ordered_nodes: list[str],
) -> tuple[LLMExpansionPolicy | None, bool]:
    """Resolve the effective expansion policy + LLM-allowed flag.

    Resolution order:

    1. Explicit ``policy`` arg from :class:`LLMExpansionRequest` wins
       outright.
    2. Otherwise, the first node in ``ordered_nodes`` that carries a v2.1
       ``expansion_policy`` hint contributes its value.
    3. Falls back to ``"source_locked"`` (the conservative default) when
       no hint exists anywhere.

    The second return value is the consensus ``llm_allowed`` flag: ``True``
    iff no node carries ``llm_allowed=False``.  A single explicit ``False``
    anywhere short-circuits the LLM path so the deterministic packet is
    returned unchanged.
    """
    llm_allowed = True
    hint_policy: LLMExpansionPolicy | None = None

    for nid in ordered_nodes:
        node = nodes_by_id.get(nid)
        if node is None:
            continue
        try:
            meta = read_v21_metadata(node)
        except Exception:
            # Malformed metadata: ignore at the policy-resolution layer.
            # The optional_metadata module already raised the validation
            # error in test environments that exercise that path.
            continue
        if meta.llm_allowed is False:
            llm_allowed = False
        if hint_policy is None and meta.expansion_policy is not None:
            hint_policy = meta.expansion_policy

    if explicit is not None:
        return explicit, llm_allowed
    if hint_policy is not None:
        return hint_policy, llm_allowed
    return "source_locked", llm_allowed


def _validate_citations(
    sections: list[GeneratedSection],
    packet_node_ids: set[str],
    acc: WarningAccumulator,
) -> list[GeneratedSection]:
    """Return only sections whose every cited node id is in *packet_node_ids*.

    Sections with one or more orphan citations are NEVER returned (the
    conservative path: rejected sections are silently dropped from the
    final ``generated_sections`` list).  One
    ``llm_citation_outside_packet`` warning is emitted per rejected
    section, with ``source_ref`` set to the section id so warnings dedup
    naturally per section.

    The function is pure — neither argument is mutated; the accumulator
    is the sole side-effect channel.
    """
    valid: list[GeneratedSection] = []
    for section in sections:
        orphans = [sid for sid in section.source_node_ids if sid not in packet_node_ids]
        if orphans:
            acc.append(
                LearningWarning(
                    severity="warning",
                    code="llm_citation_outside_packet",
                    source_ref=section.id,
                    message=(
                        f"GeneratedSection {section.id!r} cites node id(s) "
                        f"{sorted(orphans)!r} not present in packet.nodes; "
                        "section rejected and NOT attached to LSP."
                    ),
                )
            )
            continue
        valid.append(section)
    return valid


def _sort_generated_sections(
    sections: list[GeneratedSection],
) -> list[GeneratedSection]:
    """Return *sections* sorted by ``(source_node_ids[0], id)``.

    Deterministic ordering keeps content_hash stable across runs.
    A defensive empty-tuple fallback keeps the sort total — a
    GeneratedSection with no citations is not legal in the public model
    (citations are validated upstream) but the helper stays robust.
    """
    return sorted(
        sections,
        key=lambda s: (
            s.source_node_ids[0] if s.source_node_ids else "",
            s.id,
        ),
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def llm_expanded_mode(
    graph_slice: GraphSlice,
    ordered_nodes: list[str],
    request: LearningRequest,
    *,
    expansion_request: LLMExpansionRequest | None = None,
) -> tuple[LLMExpandedResult, list[LearningWarning]]:
    """Build the llm_expanded mode view.

    Pure function — never mutates ``graph_slice``, ``ordered_nodes``,
    ``request``, or ``expansion_request``.

    Parameters
    ----------
    graph_slice:
        Immutable :class:`~akms_learn.graph_import.GraphSlice` from the
        compiler pipeline.
    ordered_nodes:
        Node id list in learning order.  Iterated to walk the graph
        subgraph in a deterministic sequence.
    request:
        The validated :class:`~akms_learn.requests.LearningRequest`.  The
        ``topic`` field is forwarded to the LLM provider (unless an
        ``expansion_request.topic_override`` is supplied).
    expansion_request:
        Optional :class:`LLMExpansionRequest`.  When ``None`` a default
        instance is used — which has ``enable_llm=False``, so the
        byte-identical deterministic packet is returned unchanged.

    Returns
    -------
    (result, warnings)
        ``result`` is an :class:`LLMExpandedResult`.  ``warnings`` is the
        same list as ``result.warnings``.

    Raises
    ------
    PreconditionError
        When the caller requests a non-stub provider AND the ``llm``
        extra is absent.  The built-in stub never raises this.
    """
    cfg: LLMExpansionRequest = expansion_request or LLMExpansionRequest()

    # ------------------------------------------------------------------
    # Provider resolution: explicit > auto.
    # When LLM expansion is requested but the caller left the provider at its
    # default (the stub sentinel), auto-select a default provider by precedence:
    # configured nlm grounded → akms completion (API key) → no_provider_stub.
    # An explicitly-named non-stub provider always wins (no auto-selection).
    # When nothing is configured this resolves back to the stub, so the
    # no-provider → deterministic-packet-unchanged contract is preserved.
    # ------------------------------------------------------------------
    active_provider: str = cfg.provider
    if cfg.enable_llm and cfg.provider == NO_PROVIDER_STUB_GENERATOR:
        active_provider = resolve_default_provider()

    # ------------------------------------------------------------------
    # Capability gate — only when a non-stub provider is in play (explicit or
    # auto-selected).  The built-in stub is the always-on default and is exempt.
    # ------------------------------------------------------------------
    if cfg.enable_llm and active_provider != NO_PROVIDER_STUB_GENERATOR:
        require_capability("llm_expanded")

    # ------------------------------------------------------------------
    # Step 1 — build the deterministic packet FIRST and freeze a deep copy.
    # This is the byte-identical baseline.
    # ------------------------------------------------------------------
    deterministic_packet = _build_deterministic_packet(graph_slice, ordered_nodes)
    pre_expansion_packet: dict[str, Any] = copy.deepcopy(deterministic_packet)

    # ------------------------------------------------------------------
    # Step 2 — short-circuit when LLM expansion is disabled.
    # Returns the deterministic packet unchanged at the byte level.
    # ------------------------------------------------------------------
    if not cfg.enable_llm:
        result = LLMExpandedResult(
            packet=copy.deepcopy(pre_expansion_packet),
            pre_expansion_packet=pre_expansion_packet,
            generated_sections=[],
            policy=None,
            warnings=[],
        )
        return result, []

    # ------------------------------------------------------------------
    # Step 3 — resolve policy + llm_allowed consensus.
    # ------------------------------------------------------------------
    nodes_by_id: dict[str, dict[str, Any]] = {
        nid: dict(raw) for raw in graph_slice.nodes if (nid := raw.get("node_id")) is not None
    }
    effective_policy, llm_allowed = _resolve_policy(cfg.policy, nodes_by_id, ordered_nodes)

    # If any node forbids LLM expansion, behave as if LLM were disabled:
    # byte-identical deterministic packet.
    if not llm_allowed:
        result = LLMExpandedResult(
            packet=copy.deepcopy(pre_expansion_packet),
            pre_expansion_packet=pre_expansion_packet,
            generated_sections=[],
            policy=None,
            warnings=[],
        )
        return result, []

    # Defensive policy whitelist check — should never trigger because the
    # model enforces a Literal, but the explicit guard keeps the failure
    # mode loud rather than silent.
    if effective_policy not in LLM_EXPANSION_POLICIES:
        raise ValueError(
            f"Unknown LLMExpansionPolicy {effective_policy!r}. Allowed: {LLM_EXPANSION_POLICIES!r}"
        )

    acc = WarningAccumulator()

    # LLM expansion was requested but nothing is configured: auto-selection
    # landed on the built-in deterministic stub. That is a degraded mode, not
    # the request fulfilled, so it is reported rather than silently emitting
    # placeholder sections that look like provider output.
    if cfg.enable_llm and active_provider == NO_PROVIDER_STUB_GENERATOR:
        acc.append(
            LearningWarning(
                severity="warning",
                code="llm_no_provider_configured",
                source_ref=NO_PROVIDER_STUB_GENERATOR,
                message=(
                    "LLM expansion was requested but no provider is configured; "
                    "generated sections come from the deterministic no-provider "
                    "stub. Configure a provider (API key or NotebookLM notebook) "
                    "for real expansion."
                ),
            )
        )

    # ------------------------------------------------------------------
    # Step 4 — dispatch to the provider.
    # Unknown providers degrade to the deterministic packet and emit a
    # warning.
    # ------------------------------------------------------------------
    active_node_ids: tuple[str, ...] = tuple(deterministic_packet["node_ids"])
    topic = cfg.topic_override if cfg.topic_override is not None else request.topic

    # Dispatch through the provider seam. Every provider — the built-in
    # ``no_provider_stub`` default and the pluggable ``akms`` / ``nlm``
    # adapters (registered on import) — is resolved from the registry and
    # invoked uniformly with the full Protocol signature (so ``policy`` is
    # always supplied). An unregistered provider degrades to the
    # deterministic packet with a warning rather than raising.
    try:
        provider = resolve(active_provider)
    except PreconditionError:
        acc.append(
            LearningWarning(
                severity="warning",
                code="llm_provider_unavailable",
                source_ref=active_provider,
                message=(
                    f"LLM provider {active_provider!r} is not registered; "
                    "falling back to deterministic packet."
                ),
            )
        )
        warnings = acc.finalize()
        result = LLMExpandedResult(
            packet=copy.deepcopy(pre_expansion_packet),
            pre_expansion_packet=pre_expansion_packet,
            generated_sections=[],
            policy=effective_policy,
            warnings=warnings,
        )
        return result, warnings

    raw_sections = provider(topic, active_node_ids, effective_policy, sources=cfg.sources)

    # ------------------------------------------------------------------
    # Step 5 — citation validation (HARD invariant).
    # ------------------------------------------------------------------
    packet_node_ids: set[str] = set(deterministic_packet["node_ids"])
    valid_sections = _validate_citations(raw_sections, packet_node_ids, acc)

    # ------------------------------------------------------------------
    # Step 6 — deterministic ordering of surviving sections.
    # ------------------------------------------------------------------
    valid_sections = _sort_generated_sections(valid_sections)

    # ------------------------------------------------------------------
    # Step 7 — attach generated_sections + provenance to the packet.
    # ------------------------------------------------------------------
    final_packet: dict[str, Any] = copy.deepcopy(pre_expansion_packet)
    final_packet["generated_sections"] = [s.model_dump(mode="json") for s in valid_sections]
    # Sort the dumped representation by (source_node_ids[0], id) again so
    # the JSON-dump output is byte-stable regardless of pydantic's
    # internal dict-iteration order.
    final_packet["generated_sections"].sort(
        key=lambda d: (
            (d.get("source_node_ids") or [""])[0],
            d.get("id", ""),
        )
    )
    # Canonical provenance shape (shared with the compiler's surfaced block via
    # ``build_llm_provenance`` so the two cannot drift). The compiler rebuilds
    # the authoritative block onto the PacketBody; this one rides on
    # ``result.packet`` for mode-level callers.
    final_packet["provenance"] = {
        "llm": build_llm_provenance(
            provider=active_provider,
            model=valid_sections[0].model if valid_sections else None,
            policy=effective_policy,
            section_count=len(valid_sections),
            citation_count=sum(len(s.source_node_ids) for s in valid_sections),
            rejected_count=len(raw_sections) - len(valid_sections),
        )
    }

    warnings = acc.finalize()
    result = LLMExpandedResult(
        packet=final_packet,
        pre_expansion_packet=pre_expansion_packet,
        generated_sections=list(valid_sections),
        policy=effective_policy,
        warnings=warnings,
    )
    return result, warnings

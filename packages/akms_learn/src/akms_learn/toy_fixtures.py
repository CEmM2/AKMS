"""Toy fixture domain packs for tests and workspace mirrors.

This module ships *inside* ``src/akms_learn/`` (rather than under
``tests/fixtures/``) so that workspace-mirror tests living outside the
package tree can import the fixtures via the public ``akms_learn``
namespace. The task spec allowed either placement; we picked ``src/``
to keep the workspace-mirror import path simple.

Small ``GraphSlice`` factories that exercise the pedagogical modes without
importing or referencing any real computational-mechanics content. The
fixtures intentionally use *generic, abstract* vocabulary — widgets,
gadgets, pipelines, processes, fluxes, steps — so that downstream mode
tests can prove the deterministic modes remain domain-agnostic.

Three families, mimicking the *shape* (never the content) of the
reference compmech pack:

* :func:`fixture_graph_toy_concept_kit`        — constkit-style symbolic
  helpers: small composable concept nodes wired by ``requires`` edges.
* :func:`fixture_graph_toy_workbench`          — symbolic_fem_workbench-
  style worked examples: a worked-example node carrying Assumption,
  Derivation, and Self-check sections in approved-heading markdown form.
* :func:`fixture_graph_toy_executable_bridge`  — MechDSL-style
  spec→artifact bridge: a derivation node feeding an implementation node
  via an ``implements`` edge, plus a code-mirror node with provenance.

**Vocabulary lint contract**: no token in this module's source text or
in any returned node/edge dict may match a computational-mechanics term
(stress / strain / tensor / plasticity / material / mechanics / cauchy /
fem / mesh / yield / hyperelastic). The test
``test_no_node_id_uses_computational_mechanics_jargon`` in
``tests/test_toy_fixtures.py`` and the workspace-mirror equivalent
enforce this canary.
"""

from __future__ import annotations

from typing import Any

from akms_learn.graph_import import GraphSlice

__all__ = [
    "fixture_graph_toy_concept_kit",
    "fixture_graph_toy_workbench",
    "fixture_graph_toy_executable_bridge",
    "fixture_graph_toy_derivation_gap",
    "fixture_graph_toy_multi_granularity",
    "all_toy_fixtures",
    "RESERVED_DOMAIN_TERMS",
]


# Tokens that MUST NOT appear in any toy-fixture node id, title, tag,
# section content, or in this module's source text. Enforced by tests.
RESERVED_DOMAIN_TERMS: tuple[str, ...] = (
    "stress",
    "strain",
    "tensor",
    "plasticity",
    "material",
    # NOTE: 'mechanics' is reserved as a *domain* term; 'mechanic'-style
    # substrings (e.g. 'mechanism') would collide, so the lint test uses
    # whole-word matching to avoid false positives. The toy vocabulary
    # below sidesteps this entirely.
    "mechanics",
    "cauchy",
    "fem",
    "mesh",
    "yield",
    "hyperelastic",
)


# ---------------------------------------------------------------------------
# toy_concept_kit  — constkit-style symbolic helpers
# ---------------------------------------------------------------------------


def fixture_graph_toy_concept_kit() -> GraphSlice:
    """Concept-kit shaped fixture: three small composable concept nodes.

    Topology::

        concept_alpha  ──requires──►  concept_beta  ──requires──►  concept_gamma

    All node ids are generic (``concept_alpha`` etc.). The pack mimics a
    constkit-style "symbolic helpers" layout: each node is a tiny
    reusable building block carrying a Concept-map section.
    """
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "concept_alpha",
            "title": "Concept Alpha (toy)",
            "kind": "prerequisite",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_a",
            "tags": ["toy", "alpha", "concept_kit"],
            "status": "established",
            "source_path": "toy://concept_kit/alpha.md",
            "line_range": [1, 8],
            "extracted": {
                "Concept map": (
                    "# Concept map\n"
                    "Alpha is the smallest building block in the toy kit."
                ),
            },
        },
        {
            "node_id": "concept_beta",
            "title": "Concept Beta (toy)",
            "kind": "core_concept",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_a",
            "tags": ["toy", "beta", "concept_kit"],
            "status": "established",
            "source_path": "toy://concept_kit/beta.md",
            "line_range": [1, 12],
            "extracted": {
                "Concept map": (
                    "# Concept map\n"
                    "Beta composes two alphas via the compose helper."
                ),
            },
        },
        {
            "node_id": "concept_gamma",
            "title": "Concept Gamma (toy)",
            "kind": "core_concept",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_a",
            "tags": ["toy", "gamma", "concept_kit"],
            "status": "tentative",
            "source_path": "toy://concept_kit/gamma.md",
            "line_range": [1, 10],
            "extracted": {
                "Concept map": (
                    "# Concept map\n"
                    "Gamma is the composite produced by transforming beta."
                ),
            },
        },
    ]

    edges: list[dict[str, Any]] = [
        {
            "edge_id": "e_alpha_beta",
            "from": "concept_alpha",
            "to": "concept_beta",
            "type": "requires",
            "source_path": "toy://concept_kit/edges.md",
            "line_range": [1, 1],
        },
        {
            "edge_id": "e_beta_gamma",
            "from": "concept_beta",
            "to": "concept_gamma",
            "type": "requires",
            "source_path": "toy://concept_kit/edges.md",
            "line_range": [2, 2],
        },
    ]

    metadata: dict[str, Any] = {
        "description": (
            "Toy concept-kit fixture: generic concept helpers, "
            "no domain semantics."
        ),
        "graph_version": "toy-concept-kit-v1",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "family": "toy_concept_kit",
    }

    return GraphSlice(
        nodes=tuple(nodes), edges=tuple(edges), metadata=metadata
    )


# ---------------------------------------------------------------------------
# toy_workbench  — symbolic-workbench-style worked example
# ---------------------------------------------------------------------------


_WORKBENCH_BODY = (
    "# Learning goal\n"
    "Walk through the toy widget-pipeline derivation end-to-end.\n"
    "\n"
    "# Prerequisites\n"
    "Familiarity with the compose and transform helpers from the toy kit.\n"
    "\n"
    "# Derivation\n"
    "Step 1: start from input symbol ``s0``.\n"
    "Step 2: apply the compose helper ``c`` to obtain ``s1 = c(s0, s0)``.\n"
    "Step 3: apply the transform helper ``t`` to obtain ``s2 = t(s1)``.\n"
    "Step 4: state the assumption that ``t`` is invariant under ``c``.\n"
    "\n"
    "# Self-check\n"
    "Confirm that ``t(c(x, x)) == c(t(x), t(x))`` for the toy operators.\n"
)


def fixture_graph_toy_workbench() -> GraphSlice:
    """Worked-example fixture: derivation + assumption + self-check.

    Topology::

        workbench_prereq  ──requires──►  workbench_example
                                          (carries Derivation section)

    The ``workbench_example`` node carries an ``extracted`` mapping with a
    ``Derivation`` section using the approved-heading vocabulary. This
    proves the derivation_first mode can find a Derivation section
    in a non-computational-mechanics domain pack.
    """
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "workbench_prereq",
            "title": "Workbench Prerequisite (toy)",
            "kind": "prerequisite",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_b",
            "tags": ["toy", "workbench", "prereq"],
            "status": "established",
            "source_path": "toy://workbench/prereq.md",
            "line_range": [1, 6],
            "extracted": {
                "Prerequisites": (
                    "# Prerequisites\n"
                    "You should already know the toy compose / transform helpers."
                ),
            },
        },
        {
            "node_id": "workbench_example",
            "title": "Workbench Worked Example (toy)",
            "kind": "derivation",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_b",
            "tags": ["toy", "workbench", "derivation", "worked_example"],
            "status": "established",
            "source_path": "toy://workbench/example.md",
            "line_range": [1, 20],
            "extracted": {
                "Learning goal": (
                    "# Learning goal\n"
                    "Walk through the toy widget-pipeline derivation."
                ),
                "Prerequisites": (
                    "# Prerequisites\n"
                    "Familiarity with compose and transform."
                ),
                "Derivation": (
                    "# Derivation\n"
                    "Step 1: start from input symbol s0.\n"
                    "Step 2: s1 = compose(s0, s0).\n"
                    "Step 3: s2 = transform(s1).\n"
                    "Step 4: assume transform is invariant under compose."
                ),
                "Self-check": (
                    "# Self-check\n"
                    "Verify transform(compose(x, x)) == compose(transform(x), transform(x))."
                ),
            },
        },
    ]

    edges: list[dict[str, Any]] = [
        {
            "edge_id": "e_workbench_prereq_example",
            "from": "workbench_prereq",
            "to": "workbench_example",
            "type": "requires",
            "source_path": "toy://workbench/edges.md",
            "line_range": [1, 1],
        },
    ]

    metadata: dict[str, Any] = {
        "description": (
            "Toy workbench fixture: worked example with "
            "Derivation + Self-check sections; generic vocabulary only."
        ),
        "graph_version": "toy-workbench-v1",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "family": "toy_workbench",
        # Embed the full markdown body so tests that exercise
        # extract_sections on raw text have something to consume.
        "example_markdown_body": _WORKBENCH_BODY,
    }

    return GraphSlice(
        nodes=tuple(nodes), edges=tuple(edges), metadata=metadata
    )


# ---------------------------------------------------------------------------
# toy_executable_bridge  — MechDSL-style spec→artifact bridge
# ---------------------------------------------------------------------------


def fixture_graph_toy_executable_bridge() -> GraphSlice:
    """Spec→artifact bridge fixture with an ``implements`` edge.

    Topology::

        bridge_spec       ──implements──►  bridge_artifact
        bridge_artifact   ──refines──►     bridge_code_mirror

    * ``bridge_spec`` is a derivation-style node describing the toy
      pipeline.
    * ``bridge_artifact`` is the implementation node that the spec
      ``implements`` (this is the edge that the implementation-first mode +
      ``CodeLinkView`` consume).
    * ``bridge_code_mirror`` is a code-mirror node carrying provenance
      (source repo + path). The source path is intentionally generic so
      compiler-graceful warning paths can still be exercised when a real
      mirror is absent.

    Per task scope: source paths may be ``unknown`` to exercise the
    warning paths — we set one concrete path and leave the second as
    ``unknown`` to cover both branches.
    """
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "bridge_spec",
            "title": "Pipeline Spec Alpha (toy)",
            "kind": "derivation",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_c",
            "tags": ["toy", "bridge", "spec"],
            "status": "established",
            "source_path": "toy://bridge/spec_alpha.md",
            "line_range": [1, 14],
            "extracted": {
                "Derivation": (
                    "# Derivation\n"
                    "Spec alpha describes a three-step pipeline: "
                    "input → compose → transform → output."
                ),
            },
            "provenance": {
                "source_pack": "toy_executable_bridge",
                "kind": "spec",
            },
        },
        {
            "node_id": "bridge_artifact",
            "title": "Pipeline Artifact Alpha (toy)",
            "kind": "implementation",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_c",
            "tags": ["toy", "bridge", "artifact", "implementation"],
            "status": "tentative",
            "source_path": "toy://bridge/artifact_alpha.md",
            "line_range": [1, 10],
            "extracted": {
                "Implementation": (
                    "# Implementation\n"
                    "Artifact alpha is the compiled pipeline produced from "
                    "spec alpha by the toy code generator."
                ),
            },
            "provenance": {
                "source_pack": "toy_executable_bridge",
                "kind": "artifact",
            },
        },
        {
            "node_id": "bridge_code_mirror",
            "title": "Pipeline Code Mirror (toy)",
            "kind": "code_mirror",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_c",
            "tags": ["toy", "bridge", "code_mirror"],
            "status": "draft",
            # Intentionally 'unknown' to exercise compiler-graceful warning.
            "source_path": "unknown",
            "line_range": [0, 0],
            "extracted": {},
            "provenance": {
                "source_pack": "toy_executable_bridge",
                "code_repo": "toy://bridge/repo",
                "code_path": "unknown",
            },
        },
    ]

    edges: list[dict[str, Any]] = [
        {
            "edge_id": "e_bridge_spec_artifact",
            "from": "bridge_spec",
            "to": "bridge_artifact",
            "type": "implements",
            "source_path": "toy://bridge/edges.md",
            "line_range": [1, 1],
        },
        {
            "edge_id": "e_bridge_artifact_mirror",
            "from": "bridge_artifact",
            "to": "bridge_code_mirror",
            "type": "refines",
            "source_path": "toy://bridge/edges.md",
            "line_range": [2, 2],
        },
    ]

    metadata: dict[str, Any] = {
        "description": (
            "Toy executable-bridge fixture: spec → artifact "
            "via implements edge, plus a code-mirror node with provenance."
        ),
        "graph_version": "toy-executable-bridge-v1",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "family": "toy_executable_bridge",
    }

    return GraphSlice(
        nodes=tuple(nodes), edges=tuple(edges), metadata=metadata
    )


# ---------------------------------------------------------------------------
# toy_derivation_gap  — derivation-chain gap fixture (derivation_gap canary)
# ---------------------------------------------------------------------------


def fixture_graph_toy_derivation_gap() -> GraphSlice:
    """Gap-fixture: one derivation_step node that requires a node without derivation.

    Topology::

        gap_derivation_node  ──requires──►  gap_missing_node
        gap_implementation_node  (standalone, no derivation, no requires)

    * ``gap_derivation_node`` carries a ``Derivation`` section and requires
      ``gap_missing_node``.
    * ``gap_missing_node`` is the *target* of a ``requires`` edge from a
      derivation_step but lacks its own ``Derivation`` section — this is the
      gap that should trigger a ``derivation_gap`` warning.
    * ``gap_implementation_node`` carries only an ``Implementation`` section and
      no derivation-heavy content — it should appear after derivation nodes.

    This fixture is the derivation-gap canary for :func:`derivation_first_mode`.  The
    derivation gap should fire on ``gap_missing_node`` only; ``gap_derivation_node``
    and ``gap_implementation_node`` should NOT trigger gap warnings.
    """
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "gap_derivation_node",
            "title": "Derivation Node With Gap Dependency (toy)",
            "kind": "derivation",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_gap",
            "tags": ["toy", "gap", "derivation"],
            "status": "established",
            "source_path": "toy://gap/derivation_node.md",
            "line_range": [1, 10],
            "extracted": {
                "derivation": (
                    "# Derivation\n"
                    "Step 1: begin from the base proposition.\n"
                    "Step 2: apply the compose operator to obtain the result."
                ),
                "prerequisites": (
                    "# Prerequisites\n"
                    "Requires gap_missing_node to supply its derivation."
                ),
            },
        },
        {
            "node_id": "gap_missing_node",
            "title": "Missing Derivation Node (toy)",
            "kind": "core_concept",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_gap",
            "tags": ["toy", "gap", "missing"],
            "status": "tentative",
            "source_path": "toy://gap/missing_node.md",
            "line_range": [1, 5],
            "extracted": {
                # Intentionally missing 'derivation' section — this is the gap.
                "concept": (
                    "# Concept\n"
                    "The base proposition underpins the derivation but its own "
                    "derivation has not yet been written."
                ),
            },
        },
        {
            "node_id": "gap_implementation_node",
            "title": "Implementation Node (toy)",
            "kind": "implementation",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_gap",
            "tags": ["toy", "gap", "implementation"],
            "status": "established",
            "source_path": "toy://gap/implementation_node.md",
            "line_range": [1, 8],
            "extracted": {
                "implementation": (
                    "# Implementation\n"
                    "Concrete code that realises the pipeline described above."
                ),
            },
        },
    ]

    edges: list[dict[str, Any]] = [
        {
            "edge_id": "e_gap_derivation_missing",
            "from": "gap_derivation_node",
            "to": "gap_missing_node",
            "type": "requires",
            "source_path": "toy://gap/edges.md",
            "line_range": [1, 1],
        },
    ]

    metadata: dict[str, Any] = {
        "description": (
            "Toy derivation-gap fixture: one derivation_step node "
            "requires a node that lacks a derivation section; exercises the "
            "gap-warning path."
        ),
        "graph_version": "toy-derivation-gap-v1",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "family": "toy_derivation_gap",
    }

    return GraphSlice(
        nodes=tuple(nodes), edges=tuple(edges), metadata=metadata
    )


# ---------------------------------------------------------------------------
# toy_multi_granularity  — coarse / standard / fine granularity fixture
# ---------------------------------------------------------------------------


def fixture_graph_toy_multi_granularity() -> GraphSlice:
    """Granularity-mixed fixture: nodes tagged coarse / standard / fine.

    Topology::

        coarse_overview_alpha    (tag: coarse, id prefix: coarse_)
        std_node_beta            (tag: standard)
        fine_detail_gamma        (tag: fine, id prefix: fine_)
        fine_detail_delta        (tag: fine, id prefix: fine_)
        plain_node_epsilon       (no granularity tag, no id prefix)
                                 (domain == 'toy_domain', subdomain == 'toy_subdomain_g')

    Used by :func:`akms_learn.modes.multi_granularity.multi_granularity_mode`
    to exercise:

    * tag-based detection (``coarse`` / ``standard`` / ``fine``)
    * id-prefix detection (``coarse_*`` / ``fine_*``)
    * domain/subdomain grouping fallback (all nodes share the same domain)
    * explicit-request-selection wins over the above conventions

    All node ids and content use generic toy vocabulary per the
    toy-fixture vocabulary contract.
    """
    nodes: list[dict[str, Any]] = [
        {
            "node_id": "coarse_overview_alpha",
            "title": "Overview Alpha (toy)",
            "kind": "core_concept",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_g",
            "tags": ["toy", "coarse", "overview"],
            "status": "established",
            "source_path": "toy://granularity/overview_alpha.md",
            "line_range": [1, 6],
            "extracted": {
                "Concept map": (
                    "# Concept map\n"
                    "Alpha is the coarse-grained overview node."
                ),
            },
        },
        {
            "node_id": "std_node_beta",
            "title": "Standard Beta (toy)",
            "kind": "core_concept",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_g",
            "tags": ["toy", "standard"],
            "status": "established",
            "source_path": "toy://granularity/standard_beta.md",
            "line_range": [1, 8],
            "extracted": {
                "Concept map": (
                    "# Concept map\n"
                    "Beta is the standard-granularity node."
                ),
            },
        },
        {
            "node_id": "fine_detail_gamma",
            "title": "Detail Gamma (toy)",
            "kind": "core_concept",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_g",
            "tags": ["toy", "fine", "detail"],
            "status": "established",
            "source_path": "toy://granularity/detail_gamma.md",
            "line_range": [1, 10],
            "extracted": {
                "Concept map": (
                    "# Concept map\n"
                    "Gamma is a fine-grained deep-dive detail node."
                ),
            },
        },
        {
            "node_id": "fine_detail_delta",
            "title": "Detail Delta (toy)",
            "kind": "core_concept",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_g",
            "tags": ["toy", "fine"],
            "status": "established",
            "source_path": "toy://granularity/detail_delta.md",
            "line_range": [1, 9],
            "extracted": {
                "Concept map": (
                    "# Concept map\n"
                    "Delta is a fine-grained deep-dive detail node."
                ),
            },
        },
        {
            "node_id": "plain_node_epsilon",
            "title": "Plain Epsilon (toy)",
            "kind": "core_concept",
            "domain": "toy_domain",
            "subdomain": "toy_subdomain_g",
            "tags": ["toy"],
            "status": "established",
            "source_path": "toy://granularity/plain_epsilon.md",
            "line_range": [1, 4],
            "extracted": {
                "Concept map": (
                    "# Concept map\n"
                    "Epsilon has no granularity tag and no id prefix."
                ),
            },
        },
    ]

    edges: list[dict[str, Any]] = []

    metadata: dict[str, Any] = {
        "description": (
            "Toy multi-granularity fixture: nodes tagged "
            "coarse / standard / fine plus a plain node with no granularity "
            "signal; exercises tag-based and id-prefix detection paths."
        ),
        "graph_version": "toy-multi-granularity-v1",
        "node_count": len(nodes),
        "edge_count": len(edges),
        "family": "toy_multi_granularity",
    }

    return GraphSlice(
        nodes=tuple(nodes), edges=tuple(edges), metadata=metadata
    )


# ---------------------------------------------------------------------------
# Convenience grouping
# ---------------------------------------------------------------------------


def all_toy_fixtures() -> dict[str, GraphSlice]:
    """Return all toy fixtures keyed by family name.

    Test helpers iterate this mapping to assert family-level invariants
    (generic vocabulary, non-empty graph, schema-compatible payloads).
    """
    return {
        "toy_concept_kit": fixture_graph_toy_concept_kit(),
        "toy_workbench": fixture_graph_toy_workbench(),
        "toy_executable_bridge": fixture_graph_toy_executable_bridge(),
        "toy_derivation_gap": fixture_graph_toy_derivation_gap(),
        "toy_multi_granularity": fixture_graph_toy_multi_granularity(),
    }

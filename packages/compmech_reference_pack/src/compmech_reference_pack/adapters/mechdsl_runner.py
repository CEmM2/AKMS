"""mechdsl_runner.py — MechDSLRunner, the executable_bridge adapter.

Bridges a bounded AKMS LSP excerpt to the MechDSL Tier-1 façade
(``mechdsl.integration``) and assembles a provenance-carrying artefact dict.

Contract (the real one, NOT the spec's ``build_artifacts``)::

    build_executable(excerpt: dict, *, options: dict | None = None) -> dict

Behaviour
---------
- **Emit-only by default.** ``build_executable`` normalises the node's
  ``extracted["implementation"]`` (algpseudocode) and calls Tier-1
  ``transpile_algorithm``, and — when a ``% mechanics`` problem source plus an
  energy ``derivation`` are present — Tier-1 ``compile_from_sources``. Both are
  Taichi-free.
- **Taichi only on demand.** Tier-1 ``verify`` is called **only** when
  ``options["run_verify"]`` is truthy; that is the single Taichi-paying branch.
- **Never invalidates the packet** (spec 09 §7 rule 5): a transpile/compile
  failure is captured into ``warnings`` and reported as ``status="error"``
  only when the caller explicitly required executable output
  (``options["require_executable"]``); otherwise ``status`` stays ``"ok"``.

No-mutation invariant: this adapter never writes to any AKMS path.
"""

from __future__ import annotations

import re
from typing import Any

from akms_learn.adapters.status import AdapterStatus, adapter_registry

ADAPTER_ID = "compmech.mechdsl_runner"

__all__ = [
    "ADAPTER_ID",
    "MechDSLRunner",
    "adapter_registry_overrides",
    "available_adapter_registry",
]


def adapter_registry_overrides() -> dict[str, AdapterStatus]:
    """Registry override that marks the executable bridge available."""
    return {"executable_bridge_adapter": AdapterStatus.available}


def available_adapter_registry() -> dict[str, AdapterStatus]:
    """Return the akms_learn adapter registry with this adapter marked available."""
    return adapter_registry(adapter_registry_overrides())


def _algo_name_from_node_id(node_id: str) -> str:
    """Derive a safe algo2code algorithm name from a node id."""
    tail = node_id.rsplit(".", 1)[-1].rsplit("/", 1)[-1]
    cleaned = re.sub(r"[^0-9A-Za-z_]", "_", tail).strip("_")
    return cleaned or "algorithm"


class MechDSLRunner:
    """ExecutableBridgeAdapter implementation backed by MechDSL Tier-1.

    Satisfies ``akms_learn.adapters.protocols.ExecutableBridgeAdapter`` via
    structural subtyping (the protocol is ``@runtime_checkable``).
    """

    adapter_id = ADAPTER_ID

    # -- protocol surface ---------------------------------------------------

    def build_executable(
        self, excerpt: dict[str, Any], *, options: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Build an executable artefact from a bounded LSP excerpt.

        Returns the 8-key contract dict ``{adapter, status, emitted_source,
        transpiled, normalized_input, provenance, vv_plan, warnings}``. When
        ``options["run_verify"]`` is truthy a 9th key ``verification`` (the
        Tier-1 ``verify`` result) is added — that opt-in path is the only one
        that pays the Taichi cost. Never raises on a malformed excerpt.
        """
        options = options or {}
        run_verify = bool(options.get("run_verify", False))
        require_executable = bool(options.get("require_executable", False))

        node = self._select_node(excerpt)
        node_id = str(node.get("node_id") or excerpt.get("node_id") or "<unknown>")
        extracted = node.get("extracted")
        if not isinstance(extracted, dict):
            extracted = {}
        implementation = extracted.get("implementation")
        derivation = extracted.get("derivation")
        problem = extracted.get("problem")

        warnings: list[str] = []
        status = "ok"
        normalized_input: str | None = None
        transpiled: dict[str, Any] | None = None
        emitted_source: str | None = None

        # --- implementation -> normalize -> Tier-1 transpile (Taichi-free) ---
        if implementation:
            from compmech_reference_pack.normalize import normalize

            norm = normalize(
                implementation, algorithm_name=_algo_name_from_node_id(node_id)
            )
            normalized_input = norm.normalized
            warnings.extend(norm.warnings)
            if norm.algorithmic_block_found:
                try:
                    from mechdsl.integration import transpile_algorithm
                except ImportError as exc:
                    warnings.append(
                        "MechDSL backend unavailable; install "
                        '"compmech-reference-pack[mechdsl]" '
                        f"({type(exc).__name__}: {exc})"
                    )
                    if require_executable:
                        status = "error"
                else:
                    try:
                        transpiled = transpile_algorithm(
                            norm.normalized, backend="taichi"
                        )
                        if not transpiled.get("valid_python", False):
                            warnings.append(
                                "transpiled code did not compile as valid Python"
                            )
                            if require_executable:
                                status = "error"
                    except Exception as exc:
                        warnings.append(
                            f"transpile failed: {type(exc).__name__}: {exc}"
                        )
                        if require_executable:
                            status = "error"

        # --- derivation (+ problem) -> Tier-1 compile (Taichi-free) ----------
        if derivation and problem:
            try:
                from mechdsl.integration import compile_from_sources
            except ImportError as exc:
                warnings.append(
                    "MechDSL backend unavailable; install "
                    '"compmech-reference-pack[mechdsl]" '
                    f"({type(exc).__name__}: {exc})"
                )
                if require_executable:
                    status = "error"
            else:
                try:
                    compiled = compile_from_sources(
                        problem_source=problem, energy_source=derivation
                    )
                    emitted_source = compiled["emitted_source"]
                except Exception as exc:
                    warnings.append(
                        f"compile_from_sources failed: {type(exc).__name__}: {exc}"
                    )
                    if require_executable:
                        status = "error"
        elif derivation and not problem:
            warnings.append(
                "node carries a derivation but no '% mechanics' problem source; "
                "skipping compile_from_sources (provide extracted['problem'] to compile)"
            )

        if implementation is None and derivation is None:
            status = "error"
            warnings.append(
                f"excerpt node {node_id!r} carries neither an implementation nor a "
                "derivation; nothing to build"
            )

        result: dict[str, Any] = {
            "adapter": ADAPTER_ID,
            "status": status,
            "emitted_source": emitted_source,
            "transpiled": transpiled,
            "normalized_input": normalized_input,
            "provenance": {
                node_id: {
                    "sections": self._sections(node),
                    "references": self._references(node_id, node, excerpt),
                }
            },
            "vv_plan": self._vv_plan(node_id, node, excerpt, options),
            "warnings": warnings,
        }

        # --- the only Taichi-paying branch ----------------------------------
        if run_verify:
            result["verification"] = self._run_verify(options, warnings)

        return result

    # -- extra surface (per plan: status() / can_handle()) ------------------

    def status(self) -> dict[str, Any]:
        """Lightweight, Taichi-free availability descriptor for status routes."""
        return {
            "adapter": ADAPTER_ID,
            "available": True,
            "companion_role": "executable_bridge",
            "taichi_required_for": ["verify"],
        }

    def can_handle(self, excerpt: dict[str, Any]) -> bool:
        """True when the excerpt has a node carrying implementation/derivation.

        Total: returns ``False`` (never raises) for any malformed excerpt
        shape — missing ``nodes``, non-dict nodes, non-dict ``extracted``.
        """
        node = self._select_node(excerpt)
        extracted = node.get("extracted")
        if not isinstance(extracted, dict):
            return False
        return bool(extracted.get("implementation") or extracted.get("derivation"))

    # -- internals ----------------------------------------------------------

    @staticmethod
    def _select_node(excerpt: dict[str, Any]) -> dict[str, Any]:
        """Pick the node dict to build from.

        Accepts a node-shaped excerpt directly, a ``{"nodes": [...]}`` excerpt
        (first node carrying implementation/derivation, else the first node),
        or any dict (treated as the node).
        """
        nodes = excerpt.get("nodes")
        if isinstance(nodes, list):
            dict_nodes = [n for n in nodes if isinstance(n, dict)]
            for node in dict_nodes:
                extracted = node.get("extracted")
                if isinstance(extracted, dict) and (
                    extracted.get("implementation") or extracted.get("derivation")
                ):
                    return node
            # No build-bearing node — return the first dict node, or {} so
            # callers never touch a non-dict (None, str, …).
            return dict_nodes[0] if dict_nodes else {}
        return excerpt

    @staticmethod
    def _sections(node: dict[str, Any]) -> Any:
        return node.get("included_sections") or node.get("sections") or []

    @staticmethod
    def _references(
        node_id: str, node: dict[str, Any], excerpt: dict[str, Any]
    ) -> list[Any]:
        """Collect references attributable to this node.

        Prefers node-local references; otherwise filters packet-level
        references by ``source_node_ids`` membership (falling back to all).
        """
        node_refs = node.get("references")
        if isinstance(node_refs, list) and node_refs:
            return list(node_refs)

        packet_refs = excerpt.get("references")
        if not isinstance(packet_refs, list):
            return []
        scoped = [
            ref
            for ref in packet_refs
            if isinstance(ref, dict) and node_id in (ref.get("source_node_ids") or [])
        ]
        return scoped or list(packet_refs)

    @classmethod
    def _vv_plan(
        cls,
        node_id: str,
        node: dict[str, Any],
        excerpt: dict[str, Any],
        options: dict[str, Any],
    ) -> dict[str, Any]:
        """Assemble a verification-and-validation plan {benchmark, citation}.

        The citation is drawn from the same node-scoped reference list used for
        provenance (via :meth:`_references`), so the two never disagree.
        """
        extracted = node.get("extracted")
        if not isinstance(extracted, dict):
            extracted = {}
        benchmark = (
            options.get("benchmark")
            or extracted.get("benchmark")
            or excerpt.get("benchmark")
        )
        citation: Any = None
        for ref in cls._references(node_id, node, excerpt):
            if isinstance(ref, dict):
                citation = ref.get("citation") or ref.get("title")
                if citation:
                    break
        return {"benchmark": benchmark, "citation": citation}

    @staticmethod
    def _run_verify(options: dict[str, Any], warnings: list[str]) -> dict[str, Any]:
        """Run the single Taichi-paying Tier-1 verify branch."""
        kind = options.get("verify_kind", "patch_test")
        params = options.get("verify_params", {})

        try:
            from mechdsl.integration import verify

            return verify(kind, params)
        except ImportError as exc:
            warnings.append(
                "MechDSL backend unavailable; install "
                '"compmech-reference-pack[mechdsl]" '
                f"({type(exc).__name__}: {exc})"
            )
            return {"kind": kind, "passed": False, "details": {"error": str(exc)}}
        except Exception as exc:
            warnings.append(f"verify failed: {type(exc).__name__}: {exc}")
            return {"kind": kind, "passed": False, "details": {"error": str(exc)}}

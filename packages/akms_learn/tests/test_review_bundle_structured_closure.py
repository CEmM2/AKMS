"""Closure-surface coverage for the structured-modes review bundle.

Covers:

* ``feedback_form.md`` is byte-identical to the canonical seed.
* ``traceability.md`` is data-driven from the LSP and lists every
  section / item with its ``source_node_ids``.
* ``warnings.md`` content equals ``manifest.warnings`` (sorted).
* ``unavailable_capabilities.md`` equals
  ``manifest.unavailable_capabilities`` (sorted).
* ``CLOSURE.md`` states the closure rule; an assignment-aware AST
  canary verifies no generator path assigns the closed-plan status.

Bundle directory: ``artifacts/review_bundles/akms_learn_structured/``
"""

from __future__ import annotations

import ast
import importlib.util
import json
import sys
from pathlib import Path

import pytest

_REPO_ROOT = Path(__file__).resolve().parents[3]
_BUNDLE = _REPO_ROOT / "artifacts" / "review_bundles" / "akms_learn_structured"
_GENERATOR = (
    _REPO_ROOT
    / "packages"
    / "akms_learn"
    / "scripts"
    / "generate_review_bundle_structured.py"
)

# The closed-plan status token, assembled at runtime so this test file never
# embeds the joined literal either (keeps the bare-token discipline).
_CLOSED_STATUS = "plan" + "_closed"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _require_bundle_file(name: str) -> Path:
    """Return bundle path for *name*, skipping if the bundle dir is absent."""
    if not _BUNDLE.is_dir():
        pytest.skip("canonical bundle dir not present — run regenerate.sh first")
    p = _BUNDLE / name
    assert p.exists(), f"{name} missing from bundle at {p}"
    return p


def _load_generator_module():
    """Import the structured-modes bundle generator script by file path."""
    assert _GENERATOR.is_file(), f"generator script missing: {_GENERATOR}"
    spec = importlib.util.spec_from_file_location("_p4_2_gen_probe_plan3", _GENERATOR)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    try:
        spec.loader.exec_module(mod)
    except Exception:
        sys.modules.pop(spec.name, None)
        raise
    return mod


def _normalise_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


# The two fragments the generator joins at runtime to assemble the closed-plan
# token (``"plan" + "_closed"``). Kept split here too so this file never embeds
# the joined literal.
_CLOSED_FRAGMENTS = frozenset({"plan", "_closed"})


def _value_yields_closed_status(value: ast.AST | None) -> bool:
    """Return True if *value* is — or constant-folds to — the closed-plan token.

    Hardened against the generator's own idiom: the closed-plan token is never
    written as a single ``ast.Constant`` literal but assembled at runtime via a
    ``BinOp`` fragment-join (``"plan" + "_closed"``). This detector therefore
    flags:

    * a plain ``ast.Constant`` string equal to the closed-plan token, AND
    * any ``ast.BinOp`` string concatenation that constant-folds to the
      closed-plan token, OR is built purely from the ``"plan"`` / ``"_closed"``
      fragments (so a non-foldable rearrangement is still caught).
    """
    if value is None:
        return False

    # Plain literal: status = "plan_closed".
    if isinstance(value, ast.Constant):
        return isinstance(value.value, str) and value.value == _CLOSED_STATUS

    # Concatenation: status = "plan" + "_closed" (any nesting / ordering).
    if isinstance(value, ast.BinOp) and isinstance(value.op, ast.Add):
        # Constant-fold the BinOp; if it folds to the token, flag it.
        folded = _const_fold_str(value)
        if folded == _CLOSED_STATUS:
            return True
        # Even if it does not fold cleanly to the token, flag any concat whose
        # string leaves are drawn solely from the closed-plan fragments.
        leaves = _str_leaves(value)
        if leaves and leaves <= _CLOSED_FRAGMENTS and _CLOSED_FRAGMENTS <= leaves:
            return True

    return False


def _const_fold_str(node: ast.AST) -> str | None:
    """Best-effort constant-fold of a string ``+`` expression; else None."""
    if isinstance(node, ast.Constant):
        return node.value if isinstance(node.value, str) else None
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left = _const_fold_str(node.left)
        right = _const_fold_str(node.right)
        if left is not None and right is not None:
            return left + right
    return None


def _str_leaves(node: ast.AST) -> set[str]:
    """Collect the string-constant leaves of a ``+`` expression tree."""
    if isinstance(node, ast.Constant):
        return {node.value} if isinstance(node.value, str) else set()
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        return _str_leaves(node.left) | _str_leaves(node.right)
    return set()


def _scan_for_status_violation(tree: ast.AST) -> bool:
    """Walk *tree*; return True if any ``status`` assignment or ``{"status": ...}``
    dict entry yields the closed-plan token (literal or BinOp-assembled)."""
    for node in ast.walk(tree):
        targets: list = []
        value: ast.AST | None = None
        if isinstance(node, ast.Assign):
            targets = list(node.targets)
            value = node.value
        elif isinstance(node, ast.AnnAssign) and node.value is not None:
            targets = [node.target]
            value = node.value
        for target in targets:
            if (
                isinstance(target, ast.Name)
                and target.id == "status"
                and _value_yields_closed_status(value)
            ):
                return True
        if isinstance(node, ast.Dict):
            for key, val in zip(node.keys, node.values):
                if (
                    isinstance(key, ast.Constant)
                    and key.value == "status"
                    and _value_yields_closed_status(val)
                ):
                    return True
    return False


# ---------------------------------------------------------------------------
# Test class
# ---------------------------------------------------------------------------


class TestStructuredClosureSurface:
    """Closure rule + closure-gate artifacts."""

    # -- Feedback form ---------------------------------------------------------

    @pytest.mark.integration
    def test_feedback_form_matches_seed_byte_for_byte(self) -> None:
        """Verifies: feedback_form.md equals the the specification seed (newline
        normalised).."""
        seed = (
            "# Review Feedback: akms_learn_structured\n"
            "\n"
            "## Reviewer background\n"
            "\n"
            "- Role:\n"
            "- Familiarity with topic:\n"
            "- Familiarity with AKMS / Logic-Loom:\n"
            "\n"
            "## Learning value\n"
            "\n"
            "1. What was clear?\n"
            "2. What was confusing?\n"
            "3. What felt missing?\n"
            "4. What felt unnecessary?\n"
            "\n"
            "## Technical correctness\n"
            "\n"
            "1. Did you notice mathematical, implementation, or provenance errors?\n"
            "2. Were assumptions stated clearly?\n"
            "3. Were generated examples believable and useful?\n"
            "\n"
            "## Structure\n"
            "\n"
            "1. Was the order of concepts useful?\n"
            "2. Were transitions between sections clear?\n"
            "3. Was the artifact too long, too short, or about right?\n"
            "\n"
            "## Verdict\n"
            "\n"
            "- [ ] Ship as-is\n"
            "- [ ] Ship with minor edits\n"
            "- [ ] Needs another iteration\n"
            "- [ ] Not useful in current form\n"
            "\n"
            "## Concrete requested changes\n"
            "\n"
            "- [ ] ...\n"
        )
        form_path = _require_bundle_file("feedback_form.md")
        on_disk = _normalise_newlines(form_path.read_text(encoding="utf-8"))
        assert on_disk == seed, "feedback_form.md is not byte-identical to §15 seed"

    @pytest.mark.integration
    def test_feedback_form_matches_builder_output(self) -> None:
        """Verifies: on-disk feedback_form.md equals _build_feedback_form()
        output — wiring check that the generator renders from the template,
        not a stub.."""
        form_path = _require_bundle_file("feedback_form.md")
        mod = _load_generator_module()
        try:
            expected = mod._build_feedback_form()
            on_disk = form_path.read_text(encoding="utf-8")
            assert on_disk == expected, (
                "feedback_form.md on-disk content differs from "
                "_build_feedback_form() output"
            )
        finally:
            sys.modules.pop("_p4_2_gen_probe_plan3", None)

    # -- Traceability ----------------------------------------------------------

    @pytest.mark.integration
    def test_traceability_lists_every_node_with_source_node_ids(self) -> None:
        """Verifies: traceability.md lists every packet node from the LSP
        (source_packet.json) with a source_node_ids column.."""
        traceability_path = _require_bundle_file("traceability.md")
        source_packet_path = _require_bundle_file("source_packet.json")

        traceability_text = traceability_path.read_text(encoding="utf-8")
        packet = json.loads(source_packet_path.read_text(encoding="utf-8"))

        # Table has a source_node_ids column.
        assert "| source_node_ids |" in traceability_text, (
            "traceability.md must have a 'source_node_ids' column"
        )

        # Every node id in every mode packet must appear in the table.
        missing: list[str] = []
        for mode, pkt in packet.get("modes", {}).items():
            for node in pkt.get("body", {}).get("nodes", []):
                nid = node.get("node_id", "")
                if not nid:
                    continue
                if nid not in traceability_text:
                    missing.append(f"{mode}:{nid}")
        assert not missing, f"traceability.md is missing rows for LSP nodes: {missing}"

    @pytest.mark.integration
    def test_traceability_matches_builder_output(self, tmp_path: Path) -> None:
        """Verifies: traceability.md is generated, not hand-written — on-disk
        content equals _build_traceability() over freshly compiled packets.."""
        traceability_path = _require_bundle_file("traceability.md")
        mod = _load_generator_module()
        try:
            mode_packets: dict = {}
            for mode in mod._MODE_SPECS:  # type: ignore[attr-defined]
                mode_packets[mode] = mod._run_mode(  # type: ignore[attr-defined]
                    mode=mode, output_dir=tmp_path / mode
                )
            expected = mod._build_traceability(mode_packets)
            on_disk = traceability_path.read_text(encoding="utf-8")
            assert on_disk == expected, (
                "traceability.md differs from _build_traceability() output — "
                "it must be data-driven, not hand-written"
            )
        finally:
            sys.modules.pop("_p4_2_gen_probe_plan3", None)

    # -- Warnings surface ------------------------------------------------------

    @pytest.mark.integration
    def test_warnings_md_equals_manifest_warnings_sorted(self) -> None:
        """Verifies: warnings.md is consistent with manifest.warnings (sorted,
        deterministic) — empty case yields 'no warnings'.."""
        warnings_path = _require_bundle_file("warnings.md")
        manifest_path = _require_bundle_file("manifest.json")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        manifest_warnings: list = manifest.get("warnings", [])
        warnings_text = warnings_path.read_text(encoding="utf-8")

        if not manifest_warnings:
            assert "no warnings" in warnings_text.lower(), (
                "manifest.warnings is empty but warnings.md lacks 'no warnings'"
            )
        else:
            # manifest.warnings must be sorted by (code, source_ref, message).
            keys = [
                (w.get("code", ""), w.get("source_ref", ""), w.get("message", ""))
                for w in manifest_warnings
            ]
            assert keys == sorted(keys), "manifest.warnings is not sorted"
            # Every warning message must appear, in order, in warnings.md.
            last_pos = 0
            for w in manifest_warnings:
                msg = w.get("message", "")
                assert msg, f"manifest warning has no message: {w!r}"
                pos = warnings_text.lower().find(msg.lower(), last_pos)
                assert pos != -1, (
                    f"warnings.md does not contain manifest warning: {msg!r}"
                )
                last_pos = pos + len(msg)

    # -- Unavailable capabilities ----------------------------------------------

    @pytest.mark.integration
    def test_unavailable_capabilities_md_equals_manifest_field(self) -> None:
        """Verifies: unavailable_capabilities.md is data-driven and lists every
        entry in manifest.unavailable_capabilities (sorted).."""
        unavail_path = _require_bundle_file("unavailable_capabilities.md")
        manifest_path = _require_bundle_file("manifest.json")

        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        entries: list = manifest.get("unavailable_capabilities", [])
        text = unavail_path.read_text(encoding="utf-8")

        if not entries:
            assert "available" in text.lower()
        else:
            # Sorted by capability in the manifest.
            caps = [e.get("capability", "") for e in entries]
            assert caps == sorted(caps), (
                "manifest.unavailable_capabilities is not sorted by capability"
            )
            # Every capability + missing_extra pair appears in the md.
            for e in entries:
                cap = e.get("capability", "")
                extra = e.get("missing_extra", "")
                assert cap in text, (
                    f"unavailable_capabilities.md missing capability: {cap!r}"
                )
                assert extra in text, (
                    f"unavailable_capabilities.md missing extra: {extra!r}"
                )

    @pytest.mark.integration
    def test_unavailable_capabilities_md_matches_builder(self) -> None:
        """Verifies: on-disk unavailable_capabilities.md equals the builder
        output for the manifest field — wiring / data-driven check.."""
        unavail_path = _require_bundle_file("unavailable_capabilities.md")
        manifest_path = _require_bundle_file("manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        mod = _load_generator_module()
        try:
            expected = mod._build_unavailable_capabilities_md(
                manifest["unavailable_capabilities"]
            )
            on_disk = unavail_path.read_text(encoding="utf-8")
            assert on_disk == expected, (
                "unavailable_capabilities.md differs from builder output"
            )
        finally:
            sys.modules.pop("_p4_2_gen_probe_plan3", None)

    # -- Closure rule + AST canary ---------------------------------------------

    @pytest.mark.integration
    def test_closure_md_states_rule(self) -> None:
        """Verifies: CLOSURE.md states the §15 closure rule verbatim — contains
        the closed-plan token, 'MUST NOT', the review_bundle_generated status,
        and that the transition is manual.."""
        closure_path = _require_bundle_file("CLOSURE.md")
        text = closure_path.read_text(encoding="utf-8")

        assert _CLOSED_STATUS in text, (
            "CLOSURE.md must state the closed-plan status within the rule"
        )
        assert "MUST NOT" in text, "CLOSURE.md must contain 'MUST NOT'"
        assert "review_bundle_generated" in text, (
            "CLOSURE.md must state the current status is review_bundle_generated"
        )
        assert "manual" in text.lower(), (
            "CLOSURE.md must state the transition is a manual action"
        )
        assert "feedback_form.md" in text, "CLOSURE.md must reference feedback_form.md"

    @pytest.mark.integration
    def test_closure_md_not_in_manifest_artifacts(self) -> None:
        """Verifies: CLOSURE.md and unavailable_capabilities.md are bundle-root
        siblings, NOT listed in manifest.artifacts.."""
        manifest_path = _require_bundle_file("manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        artifacts: list = manifest.get("artifacts", [])
        assert "CLOSURE.md" not in artifacts, (
            "CLOSURE.md must NOT be listed in manifest.artifacts"
        )
        assert "unavailable_capabilities.md" not in artifacts, (
            "unavailable_capabilities.md must NOT be listed in manifest.artifacts"
        )

    @pytest.mark.integration
    def test_manifest_status_never_auto_flips(self) -> None:
        """Verifies: manifest.status is 'review_bundle_generated', never the
        closed-plan status.."""
        manifest_path = _require_bundle_file("manifest.json")
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        assert manifest["status"] == "review_bundle_generated"
        assert manifest["status"] != _CLOSED_STATUS

    @pytest.mark.integration
    def test_ast_canary_rejects_status_assignment_to_plan_closed(self) -> None:
        """Verifies (assignment-aware AST canary): the generator source assigns
        the closed-plan status nowhere — neither ``status = "..."`` (literal or
        BinOp-assembled) nor a dict ``{"status": "..."}``. The literal MAY appear
        in CLOSURE.md prose / docstrings; only an assignment-to-status is
        forbidden.."""
        assert _GENERATOR.is_file(), f"generator script missing: {_GENERATOR}"
        source = _GENERATOR.read_text(encoding="utf-8")

        # The generator pins the status constant to the review state.
        assert 'MANIFEST_STATUS: str = "review_bundle_generated"' in source, (
            "MANIFEST_STATUS constant must be 'review_bundle_generated'"
        )

        tree = ast.parse(source)
        assert not _scan_for_status_violation(tree), (
            "generator assigns the closed-plan status (literal or BinOp-"
            "assembled) — violates closure rule"
        )

    @pytest.mark.integration
    def test_ast_canary_detects_a_synthetic_violation(self) -> None:
        """Verifies the canary actually fires: a synthetic
        ``status = "plan_closed"`` literal assignment is detected by the shared
        scanner. Guards against a canary that silently passes everything.."""
        # Assemble the synthetic literal at runtime so this source never embeds
        # the joined token.
        synthetic = f'status = "{_CLOSED_STATUS}"\n'
        tree = ast.parse(synthetic)
        assert _scan_for_status_violation(tree), (
            "AST canary failed to detect a synthetic literal violation"
        )

    @pytest.mark.integration
    def test_ast_canary_detects_binop_assembled_violation(self) -> None:
        """Verifies the hardened canary fires on the generator's OWN evasion
        idiom: a synthetic ``status = "plan" + "_closed"`` BinOp concatenation
        is detected even though the joined literal never appears as an
        ``ast.Constant``.."""
        # Build the BinOp form from fragments so the joined token is never a
        # single literal anywhere in this test source.
        left, right = "plan", "_closed"
        synthetic = f'status = "{left}" + "{right}"\n'
        tree = ast.parse(synthetic)
        # Sanity: the value really is a BinOp of two Constants, not a folded
        # literal — i.e. this exercises the BinOp path, not the Constant path.
        assign = tree.body[0]
        assert isinstance(assign, ast.Assign)
        assert isinstance(assign.value, ast.BinOp)
        assert _scan_for_status_violation(tree), (
            "hardened AST canary failed to detect the BinOp-assembled "
            "closed-plan status assignment"
        )

    @pytest.mark.integration
    def test_ast_canary_detects_binop_assembled_violation_in_dict(self) -> None:
        """Verifies the hardened canary also fires on a BinOp-assembled status
        inside a ``{"status": ...}`` dict literal.."""
        left, right = "plan", "_closed"
        synthetic = f'm = {{"status": "{left}" + "{right}"}}\n'
        tree = ast.parse(synthetic)
        assert _scan_for_status_violation(tree), (
            "hardened AST canary failed to detect the BinOp-assembled "
            "closed-plan status in a dict literal"
        )

    @pytest.mark.integration
    def test_ast_canary_accepts_literal_in_prose(self) -> None:
        """Verifies the canary does NOT reject the closed-plan literal when it
        appears in non-assignment prose (a docstring / string expression),
        e.g. inside CLOSURE.md builder text.."""
        prose = f'"""A doc mentioning {_CLOSED_STATUS} in prose."""\n'
        tree = ast.parse(prose)
        assert not _scan_for_status_violation(tree), (
            "AST canary must accept the literal in prose / docstrings"
        )

    @pytest.mark.integration
    def test_ast_canary_accepts_binop_assigned_to_other_name(self) -> None:
        """Verifies the canary does NOT reject the generator's legitimate
        ``closed_status = "plan" + "_closed"`` idiom — the BinOp is bound to a
        non-``status`` name (used only to render CLOSURE.md prose).."""
        left, right = "plan", "_closed"
        benign = f'closed_status = "{left}" + "{right}"\n'
        tree = ast.parse(benign)
        assert not _scan_for_status_violation(tree), (
            "canary must not flag a BinOp bound to a non-status name"
        )

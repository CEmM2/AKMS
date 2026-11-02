"""The query command's answer output: default answer, --no-answer, --json and insufficient context."""

from __future__ import annotations

import json
import re
from pathlib import Path

import pytest

from akms.repo_wiki.answer import INSUFFICIENT_CONTEXT_MSG
from akms.repo_wiki.cli import main
from .test_build_render_graph_summary import copy_fixture

FIXTURES = Path(__file__).resolve().parent / "fixtures"

FIXTURE_SRC = FIXTURES / "tiny_repo"
KNOWN_SYMBOL = "pkg.core.Greeter.greet"
ABSENT_QUERY = "totally_nonexistent_symbol_xyz_abc_qrs"


@pytest.fixture()
def built_repo(tmp_path: Path) -> Path:
    """Tiny repo with wiki built (no summaries)."""
    copy_fixture(FIXTURE_SRC, tmp_path)
    assert main(["--repo-root", str(tmp_path), "build", "--no-summaries"]) == 0
    return tmp_path


def test_default_query_emits_answer_block(built_repo: Path, capsys):
    """Default mode (no --no-answer) prints 'Answer:' header when context is retrievable."""
    capsys.readouterr()
    rc = main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL])
    assert rc == 0
    output = capsys.readouterr().out
    assert "Answer:" in output, (
        f"Expected 'Answer:' in default query output.\nGot:\n{output}"
    )


def test_default_query_answer_is_non_empty(built_repo: Path, capsys):
    """For a known symbol, the answer block must contain at least one claim line."""
    capsys.readouterr()
    rc = main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL])
    assert rc == 0
    output = capsys.readouterr().out
    # After "Answer:" there must be at least one non-empty line.
    answer_section = output.split("Answer:", 1)[-1].strip()
    assert answer_section, "Answer block must be non-empty for a known symbol"


def test_no_answer_suppresses_answer_block(built_repo: Path, capsys):
    """--no-answer must not print 'Answer:' header."""
    capsys.readouterr()
    rc = main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--no-answer"])
    assert rc == 0
    output = capsys.readouterr().out
    assert "Answer:" not in output, "--no-answer must suppress the Answer block"


def test_no_answer_omits_reserved_answer_placeholder(built_repo: Path, capsys):
    """The 'Answer generation is reserved' placeholder never appears under --no-answer."""
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--no-answer"])
    output = capsys.readouterr().out
    assert "Answer generation is reserved" not in output


def test_no_answer_still_shows_context(built_repo: Path, capsys):
    """--no-answer still prints the 'Context:' section."""
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--no-answer"])
    output = capsys.readouterr().out
    assert "Context:" in output


def test_json_output_has_answer_key(built_repo: Path, capsys):
    """--json output must include top-level 'answer' key."""
    capsys.readouterr()
    rc = main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--json"])
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "answer" in payload, (
        f"Expected 'answer' key in JSON. Keys: {list(payload.keys())}"
    )


def test_json_output_has_insufficient_context_boolean(built_repo: Path, capsys):
    """'answer.insufficient_context' must be a boolean."""
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload["answer"]["insufficient_context"], bool)


def test_json_output_has_claims_list(built_repo: Path, capsys):
    """'answer.claims' must be a list."""
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert isinstance(payload["answer"]["claims"], list)


def test_json_output_existing_keys_preserved(built_repo: Path, capsys):
    """The query, results and context keys stay in the JSON output next to the answer."""
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--json"])
    payload = json.loads(capsys.readouterr().out)
    for key in ("query", "results", "context"):
        assert key in payload, f"'{key}' missing from JSON output"


def test_json_insufficient_context_exit_code_zero(built_repo: Path, capsys):
    """Insufficient context is a normal answer — exit code must be 0."""
    capsys.readouterr()
    rc = main(["--repo-root", str(built_repo), "query", ABSENT_QUERY, "--json"])
    assert rc == 0


def test_json_insufficient_context_flag_is_true(built_repo: Path, capsys):
    """When context is insufficient, 'answer.insufficient_context' must be True."""
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", ABSENT_QUERY, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["answer"]["insufficient_context"] is True


def test_json_claims_evidence_kind_field(built_repo: Path, capsys):
    """Each claim in JSON must have an 'evidence_kind' field."""
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--json"])
    payload = json.loads(capsys.readouterr().out)
    answer = payload["answer"]
    if not answer["insufficient_context"]:
        for claim in answer["claims"]:
            assert "evidence_kind" in claim, f"Claim missing 'evidence_kind': {claim}"


def test_json_no_answer_combined_returns_empty_claims(built_repo: Path, capsys):
    """--json + --no-answer: answer section present but claims list is empty."""
    capsys.readouterr()
    rc = main(
        ["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--json", "--no-answer"]
    )
    assert rc == 0
    payload = json.loads(capsys.readouterr().out)
    assert "answer" in payload
    assert payload["answer"]["claims"] == []


def test_insufficient_context_exit_code_zero(built_repo: Path, capsys):
    """Absent symbol: exit code is 0 (insufficient context is not an error)."""
    capsys.readouterr()
    rc = main(["--repo-root", str(built_repo), "query", ABSENT_QUERY])
    assert rc == 0


def test_insufficient_context_shows_canonical_message(built_repo: Path, capsys):
    """Absent symbol: canonical INSUFFICIENT_CONTEXT_MSG must appear in stdout."""
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", ABSENT_QUERY])
    output = capsys.readouterr().out
    assert INSUFFICIENT_CONTEXT_MSG in output


def test_default_query_cites_path_and_line_range(built_repo: Path, capsys):
    """The answer cites sources as path:Lstart-Lend."""
    assert main(["--repo-root", str(built_repo), "query", "Greeter.greet"]) == 0
    assert re.search(r"\S+\.py:L\d+-\d+", capsys.readouterr().out)


def test_dotted_query_claims_are_cited_and_labelled(built_repo: Path, capsys):
    """A module-prefix hit yields cited claims carrying its match label, in text and JSON."""
    capsys.readouterr()
    assert main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL]) == 0
    output = capsys.readouterr().out
    assert "pkg/core.py:L12-14 [match: module-prefix]" in output
    assert (
        "pkg/core.py:L12-14: [source] python:pkg/core.py::Greeter.greet [match: module-prefix]"
        in output
    )

    main(["--repo-root", str(built_repo), "query", KNOWN_SYMBOL, "--json"])
    payload = json.loads(capsys.readouterr().out)
    assert payload["results"][0]["resolution"] == "module-prefix"
    assert payload["answer"]["insufficient_context"] is False
    assert all(claim["citations"] for claim in payload["answer"]["claims"])


def test_partial_suffix_claims_are_cited_inferences(built_repo: Path, capsys):
    """A suffix fallback hit is answered as a cited, labelled inference, never as plain source."""
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", "pkg.Greeter.greet", "--json"])
    payload = json.loads(capsys.readouterr().out)
    labelled = [
        c for c in payload["answer"]["claims"] if "[match: partial-suffix]" in c["text"]
    ]
    assert labelled
    assert all(c["evidence_kind"] == "inference" and c["citations"] for c in labelled)


def test_dotted_total_miss_reports_insufficient_context(built_repo: Path, capsys):
    capsys.readouterr()
    main(["--repo-root", str(built_repo), "query", "nowhere.qqq_missing.zzz_absent"])
    assert INSUFFICIENT_CONTEXT_MSG in capsys.readouterr().out

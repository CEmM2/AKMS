"""Answer provider behaviour: citation validation, insufficient context, evidence ordering and prompts."""

from __future__ import annotations

import inspect

import pytest

from akms.repo_wiki.answer import (
    INSUFFICIENT_CONTEXT_MSG,
    AnswerProvider,
    AnswerResult,
    Citation,
    Claim,
    LocalContextOnlyAnswerProvider,
    _validate_block,
)
from akms.repo_wiki.index import SearchResult
from akms.repo_wiki.retrieve import ContextBlock, ContextPack, NormalizedQuery


def _query(text: str = "how does X work?") -> NormalizedQuery:
    return NormalizedQuery(raw=text, text=text, kind="natural_language")


def _result(
    doc_id: str = "mod.sym",
    path: str = "src/mod.py",
    start_line: int = 1,
    end_line: int = 10,
    doc_type: str = "symbol",
    symbol_id: str = "",
    module: str = "",
    title: str = "",
    content: str = "some code",
) -> SearchResult:
    return SearchResult(
        doc_id=doc_id,
        doc_type=doc_type,
        path=path,
        content=content,
        score=1.0,
        module=module,
        symbol_id=symbol_id,
        kind="function",
        start_line=start_line,
        end_line=end_line,
        repo_commit="abc123",
        content_hash="sha256:abc",
        title=title or doc_id,
    )


def _block(
    doc_id: str = "mod.sym",
    path: str = "src/mod.py",
    start_line: int = 1,
    end_line: int = 10,
    doc_type: str = "symbol",
    symbol_id: str = "",
    module: str = "",
    title: str = "",
    role: str = "result",
) -> ContextBlock:
    return ContextBlock(
        role=role,
        result=_result(
            doc_id=doc_id,
            path=path,
            start_line=start_line,
            end_line=end_line,
            doc_type=doc_type,
            symbol_id=symbol_id,
            module=module,
            title=title,
        ),
    )


def _pack(*blocks: ContextBlock, question: str = "how does X work?") -> ContextPack:
    q = _query(question)
    results = [b.result for b in blocks]
    return ContextPack(query=q, results=results, context=list(blocks))


class TestAnswerProviderIsAbstract:
    def test_cannot_instantiate_base_class(self):
        """AnswerProvider must not be directly instantiatable."""
        assert inspect.isabstract(AnswerProvider), "AnswerProvider must be abstract"
        with pytest.raises(TypeError):
            AnswerProvider()  # type: ignore[abstract]

    def test_concrete_provider_is_instantiatable(self):
        """LocalContextOnlyAnswerProvider is a valid concrete implementation."""
        p = LocalContextOnlyAnswerProvider()
        assert isinstance(p, AnswerProvider)


class TestCitationValidation:
    def test_valid_block_passes(self):
        block = _block(path="src/foo.py", start_line=1, end_line=10)
        assert _validate_block(block) is None

    def test_missing_path_fails(self):
        block = _block(path="")
        error = _validate_block(block)
        assert error is not None
        assert "path" in error.lower()

    def test_negative_start_line_fails(self):
        block = _block(start_line=-1, end_line=10)
        error = _validate_block(block)
        assert error is not None
        assert "start_line" in error

    def test_negative_end_line_fails(self):
        block = _block(start_line=1, end_line=-5)
        error = _validate_block(block)
        assert error is not None
        assert "end_line" in error

    def test_zero_start_line_is_valid(self):
        # Line 0 is allowed (some tools use 0-based or module-level)
        block = _block(start_line=0, end_line=0)
        assert _validate_block(block) is None


class TestInsufficientContext:
    def test_empty_pack_has_canonical_phrase(self):
        provider = LocalContextOnlyAnswerProvider()
        pack = ContextPack(query=_query(), results=[], context=[])
        result = provider.answer(pack, "What does init() do?")
        assert result.insufficient_context is True
        assert INSUFFICIENT_CONTEXT_MSG in result.insufficient_context_reason

    def test_all_invalid_blocks_have_canonical_phrase(self):
        provider = LocalContextOnlyAnswerProvider()
        bad_block = _block(path="")  # invalid — no path
        pack = _pack(bad_block)
        result = provider.answer(pack, "What does init() do?")
        assert result.insufficient_context is True
        assert INSUFFICIENT_CONTEXT_MSG in result.insufficient_context_reason

    def test_canonical_phrase_constant_matches_message(self):
        """The canonical phrase exported from the module matches what ends up in results."""
        provider = LocalContextOnlyAnswerProvider()
        pack = ContextPack(query=_query(), results=[], context=[])
        result = provider.answer(pack, "?")
        # The constant itself must appear verbatim in the reason
        assert INSUFFICIENT_CONTEXT_MSG == result.insufficient_context_reason


class TestRenderedPrompt:
    def test_prompt_contains_question(self):
        provider = LocalContextOnlyAnswerProvider()
        question = "How does the scheduler work?"
        pack = _pack(_block(), question=question)
        result = provider.answer(pack, question)
        assert question in result.prompt

    def test_prompt_contains_citation_guidance(self):
        provider = LocalContextOnlyAnswerProvider()
        pack = _pack(_block())
        result = provider.answer(pack, "test?")
        # Design doc section 29.2 rules must appear in the prompt
        assert "Cite source file paths and line ranges" in result.prompt

    def test_prompt_contains_context_block(self):
        provider = LocalContextOnlyAnswerProvider()
        b = _block(path="src/trainer.py", start_line=1, end_line=50)
        pack = _pack(b)
        result = provider.answer(pack, "?")
        assert "src/trainer.py" in result.prompt

    def test_prompt_mentions_insufficient_when_empty(self):
        provider = LocalContextOnlyAnswerProvider()
        pack = ContextPack(query=_query(), results=[], context=[])
        result = provider.answer(pack, "?")
        # Even when insufficient, a prompt is still rendered
        assert result.prompt != ""


class TestMixedBlocks:
    def test_valid_blocks_produce_claims_despite_invalid_sibling(self):
        """Invalid blocks are excluded; valid blocks still yield claims."""
        provider = LocalContextOnlyAnswerProvider()
        valid = _block("valid_sym", path="src/mod.py", start_line=5, end_line=20)
        invalid = _block("bad_sym", path="")  # no path
        pack = _pack(invalid, valid)
        result = provider.answer(pack, "?")
        assert not result.insufficient_context
        assert len(result.claims) == 1
        assert result.claims[0].evidence_kind == "source"

    def test_mixed_pack_citations_only_include_valid(self):
        provider = LocalContextOnlyAnswerProvider()
        valid = _block("valid_sym", path="src/mod.py", start_line=5, end_line=20)
        invalid = _block("bad_sym", path="")
        pack = _pack(invalid, valid)
        result = provider.answer(pack, "?")
        assert all(c.path != "" for c in result.citations)


class TestSummaryOnlyPack:
    def test_all_claims_are_secondary_in_summary_only_pack(self):
        provider = LocalContextOnlyAnswerProvider()
        s1 = _block(
            "a.summary", doc_type="summary", path="src/a.py", start_line=1, end_line=5
        )
        s2 = _block(
            "b.summary", doc_type="summary", path="src/b.py", start_line=1, end_line=5
        )
        pack = _pack(s1, s2)
        result = provider.answer(pack, "?")
        assert not result.insufficient_context
        for claim in result.claims:
            assert claim.evidence_kind == "summary"
        for citation in result.citations:
            assert citation.secondary is True

    def test_no_source_claims_in_summary_only_pack(self):
        provider = LocalContextOnlyAnswerProvider()
        s = _block("s", doc_type="summary", path="src/s.py", start_line=1, end_line=5)
        pack = _pack(s)
        result = provider.answer(pack, "?")
        source_claims = [c for c in result.claims if c.evidence_kind == "source"]
        assert source_claims == []


class TestContextOnlyMode:
    def test_context_only_returns_no_claims(self):
        provider = LocalContextOnlyAnswerProvider()
        b = _block("sym", path="src/foo.py", start_line=1, end_line=10)
        pack = _pack(b)
        result = provider.context_only(pack, "?")
        assert result.claims == []

    def test_context_only_returns_citations_for_valid_blocks(self):
        provider = LocalContextOnlyAnswerProvider()
        b = _block("sym", path="src/foo.py", start_line=1, end_line=10)
        pack = _pack(b)
        result = provider.context_only(pack, "?")
        assert len(result.citations) == 1
        assert result.citations[0].path == "src/foo.py"

    def test_context_only_empty_pack_is_insufficient(self):
        provider = LocalContextOnlyAnswerProvider()
        pack = ContextPack(query=_query(), results=[], context=[])
        result = provider.context_only(pack, "?")
        assert result.insufficient_context is True


class TestCitationLabel:
    def test_source_citation_label_uses_line_format(self):
        c = Citation(path="src/foo.py", start_line=10, end_line=20, doc_type="symbol")
        assert c.label == "src/foo.py:L10-20"

    def test_secondary_citation_with_symbol_id(self):
        c = Citation(
            path="src/foo.py",
            start_line=10,
            end_line=20,
            doc_type="summary",
            symbol_id="src.foo.MyClass",
            secondary=True,
        )
        assert c.label == "generated summary for src.foo.MyClass"

    def test_overlay_citation_uses_path(self):
        c = Citation(
            path=".repo_wiki/overlays/architecture.md",
            start_line=1,
            end_line=5,
            doc_type="overlay",
        )
        # overlay is not marked secondary by default, so label is path
        assert c.label == ".repo_wiki/overlays/architecture.md"


class TestAnswerResultShape:
    def test_result_has_required_fields(self):
        result = AnswerResult(question="test?")
        assert result.question == "test?"
        assert result.claims == []
        assert result.citations == []
        assert result.insufficient_context is False
        assert result.prompt == ""

    def test_claim_has_evidence_kind(self):
        claim = Claim(text="foo is bar", evidence_kind="source")
        assert claim.evidence_kind == "source"
        assert claim.citations == []


def test_source_claims_precede_summary_and_overlay_claims():
    """Source-backed claims come first even when summaries and overlays are listed earlier."""
    summary = _block(
        "loader.load.summary",
        doc_type="summary",
        path="src/data/loader.py",
        start_line=10,
        end_line=30,
    )
    overlay = _block(
        "arch_overlay",
        doc_type="overlay",
        path=".repo_wiki/overlays/architecture.md",
        start_line=1,
        end_line=5,
    )
    source = _block(
        "loader.load",
        doc_type="symbol",
        path="src/data/loader.py",
        start_line=10,
        end_line=30,
    )

    result = LocalContextOnlyAnswerProvider().answer(
        _pack(summary, overlay, source), "How does loading work?"
    )

    kinds = [claim.evidence_kind for claim in result.claims]
    assert kinds[0] == "source"
    assert "source" not in kinds[1:]
    assert len(kinds) == 3
    assert [citation.secondary for citation in result.citations] == [False, True, True]

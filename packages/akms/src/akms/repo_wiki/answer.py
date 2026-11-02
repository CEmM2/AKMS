"""Answer provider grounded only in the supplied ContextPack; source citations first."""

from __future__ import annotations

import abc
import textwrap
from dataclasses import dataclass, field
from typing import Literal

from akms.repo_wiki.retrieve import ContextBlock, ContextPack

# Grep-stable insufficient-context phrase (shared by the CLI and tests).
INSUFFICIENT_CONTEXT_MSG = (
    "Insufficient context: the retrieved context does not contain enough "
    "cited source information to answer this question."
)

EvidenceKind = Literal["source", "summary", "inference"]

CITATION_FORMAT = "{path}:L{start}-{end}"


@dataclass
class Citation:
    """A single source-location citation attached to a claim or answer."""

    path: str
    start_line: int
    end_line: int
    doc_type: str = "symbol"  # "symbol" | "module" | "overlay" | "summary"
    symbol_id: str = ""
    secondary: bool = False  # True when this is a generated-summary citation

    @property
    def label(self) -> str:
        if self.doc_type in {"symbol", "module"} and not self.secondary:
            return CITATION_FORMAT.format(
                path=self.path, start=self.start_line, end=self.end_line
            )
        if self.secondary and self.symbol_id:
            return f"generated summary for {self.symbol_id}"
        if self.secondary:
            return f"generated summary for {self.path}"
        return self.path


@dataclass
class Claim:
    """A single factual assertion derived from retrieved context."""

    text: str
    evidence_kind: EvidenceKind
    citations: list[Citation] = field(default_factory=list)


@dataclass
class AnswerResult:
    """Structured result returned by any AnswerProvider."""

    question: str
    claims: list[Claim] = field(default_factory=list)
    citations: list[Citation] = field(default_factory=list)
    insufficient_context: bool = False
    insufficient_context_reason: str = ""
    prompt: str = ""  # Rendered prompt for transparency / CLI display


def _validate_block(block: ContextBlock) -> str | None:
    """Return an error string if the block is missing required citation metadata, else None."""
    result = block.result
    path = result.path or ""
    if not path:
        return f"block '{result.doc_id}' has no path"
    if result.start_line < 0:
        return f"block '{result.doc_id}' has negative start_line ({result.start_line})"
    if result.end_line < 0:
        return f"block '{result.doc_id}' has negative end_line ({result.end_line})"
    return None


def _is_summary_block(block: ContextBlock) -> bool:
    return block.result.doc_type in {"summary", "overlay"}


def _is_source_block(block: ContextBlock) -> bool:
    return block.result.doc_type in {"symbol", "module"}


def _order_blocks(blocks: list[ContextBlock]) -> list[ContextBlock]:
    """Order blocks source-first, then other, then summary/secondary (stable within groups)."""
    source = [b for b in blocks if _is_source_block(b)]
    summary = [b for b in blocks if _is_summary_block(b)]
    other = [b for b in blocks if not _is_source_block(b) and not _is_summary_block(b)]
    return source + other + summary


def _resolution_suffix(resolution: str) -> str:
    return f" [match: {resolution}]" if resolution else ""


def _block_to_citation(block: ContextBlock, *, secondary: bool = False) -> Citation:
    return Citation(
        path=block.result.path,
        start_line=block.result.start_line,
        end_line=block.result.end_line,
        doc_type=block.result.doc_type,
        symbol_id=block.result.symbol_id,
        secondary=secondary,
    )


class AnswerProvider(abc.ABC):
    """Abstract answer provider: a pure function of the ContextPack and question (no I/O)."""

    @abc.abstractmethod
    def answer(self, pack: ContextPack, question: str) -> AnswerResult:
        """Generate a grounded answer; ``insufficient_context`` if no block validates."""

    @abc.abstractmethod
    def context_only(self, pack: ContextPack, question: str) -> AnswerResult:
        """Return context without claims (``--no-answer``); ``prompt`` is still rendered."""


class LocalContextOnlyAnswerProvider(AnswerProvider):
    """Default no-LLM provider: one ``Claim`` per valid block, source blocks first."""

    def answer(self, pack: ContextPack, question: str) -> AnswerResult:
        valid_blocks, invalid_reasons = self._partition_blocks(pack)
        prompt = self._render_prompt(question, valid_blocks)

        if not valid_blocks:
            return AnswerResult(
                question=question,
                insufficient_context=True,
                insufficient_context_reason=INSUFFICIENT_CONTEXT_MSG,
                prompt=prompt,
            )

        ordered = _order_blocks(valid_blocks)

        claims: list[Claim] = []
        citations: list[Citation] = []
        seen_citation_keys: set[str] = set()

        for block in ordered:
            evidence_kind = self._evidence_kind(block)
            is_secondary = _is_summary_block(block)
            citation = _block_to_citation(block, secondary=is_secondary)
            claim_text = self._claim_text(block, evidence_kind)
            claim = Claim(
                text=claim_text,
                evidence_kind=evidence_kind,
                citations=[citation],
            )
            claims.append(claim)
            if citation.label not in seen_citation_keys:
                citations.append(citation)
                seen_citation_keys.add(citation.label)

        return AnswerResult(
            question=question,
            claims=claims,
            citations=citations,
            insufficient_context=False,
            prompt=prompt,
        )

    def context_only(self, pack: ContextPack, question: str) -> AnswerResult:
        """Return a no-claim result (for ``--no-answer`` mode)."""
        valid_blocks, _ = self._partition_blocks(pack)
        prompt = self._render_prompt(question, valid_blocks)
        is_insufficient = not valid_blocks

        citations: list[Citation] = []
        seen_citation_keys: set[str] = set()
        for block in _order_blocks(valid_blocks):
            citation = _block_to_citation(block, secondary=_is_summary_block(block))
            if citation.label not in seen_citation_keys:
                citations.append(citation)
                seen_citation_keys.add(citation.label)

        return AnswerResult(
            question=question,
            claims=[],
            citations=citations,
            insufficient_context=is_insufficient,
            insufficient_context_reason=INSUFFICIENT_CONTEXT_MSG
            if is_insufficient
            else "",
            prompt=prompt,
        )

    def _partition_blocks(
        self, pack: ContextPack
    ) -> tuple[list[ContextBlock], list[str]]:
        """Split pack.context into (valid_blocks, validation_error_reasons)."""
        valid: list[ContextBlock] = []
        errors: list[str] = []
        for block in pack.context:
            error = _validate_block(block)
            if error:
                errors.append(error)
            else:
                valid.append(block)
        return valid, errors

    @staticmethod
    def _evidence_kind(block: ContextBlock) -> EvidenceKind:
        doc_type = block.result.doc_type
        # A partial-suffix hit is a guess at what the query meant, not direct evidence for it.
        if block.result.resolution == "partial-suffix":
            return "inference"
        if doc_type in {"symbol", "module"}:
            return "source"
        if doc_type in {"summary", "overlay"}:
            return "summary"
        return "inference"

    @staticmethod
    def _claim_text(block: ContextBlock, evidence_kind: EvidenceKind) -> str:
        result = block.result
        title = result.title or result.doc_id
        if evidence_kind == "summary":
            symbol = result.symbol_id or result.module or result.doc_id
            return f"[summary] generated summary for {symbol}"
        return f"[{evidence_kind}] {title}{_resolution_suffix(result.resolution)}"

    @staticmethod
    def _render_prompt(question: str, valid_blocks: list[ContextBlock]) -> str:
        """Render the answer prompt template."""
        context_lines: list[str] = []
        for block in valid_blocks:
            result = block.result
            citation = CITATION_FORMAT.format(
                path=result.path, start=result.start_line, end=result.end_line
            )
            title = result.title or result.doc_id
            context_lines.append(
                f"[{citation}] {title}{_resolution_suffix(result.resolution)}"
            )
            if result.content:
                snippet = textwrap.shorten(result.content, width=300, placeholder="...")
                context_lines.append(f"  {snippet}")

        context_text = (
            "\n".join(context_lines) if context_lines else "(no cited context)"
        )

        return textwrap.dedent(f"""\
            You are answering questions about a private code repository.
            Use only the provided context.
            Rules:
            - Cite source file paths and line ranges.
            - If context is insufficient, say what is missing.
            - Distinguish direct evidence from inference.
            - Do not claim behavior that is not supported by retrieved context.
            - Prefer concrete symbols, files, and functions.
            User question:
            {question}
            Retrieved context:
            {context_text}
        """)

"""Privacy-first local summary generation."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from akms.repo_wiki.hashing import sha256_text
from akms.repo_wiki.models import ParsedModule, Symbol
from akms.repo_wiki.paths import ensure_parent, read_source, safe_doc_name
from akms.repo_wiki.render_markdown import repo_commit, write_symbol_doc

CACHE_PATH = ".repo_wiki/cache/llm_summaries.json"


class SummaryProvider(Protocol):
    name: str

    def summarize_symbol(self, symbol: Symbol) -> str | None:
        """Return a summary, or None when the provider is intentionally disabled."""


@dataclass(slots=True)
class DisabledSummaryProvider:
    name: str = "disabled"

    def summarize_symbol(self, symbol: Symbol) -> str | None:
        return None


@dataclass(slots=True)
class LocalSummaryProvider:
    name: str = "local"

    def summarize_symbol(self, symbol: Symbol) -> str:
        return local_symbol_summary(symbol)


@dataclass(slots=True)
class RemoteSummaryProvider:
    name: str
    allow_source_code_upload: bool = False

    def summarize_symbol(self, symbol: Symbol) -> str:
        if not self.allow_source_code_upload:
            raise ValueError("remote summaries require allow_source_code_upload: true")
        raise NotImplementedError("remote providers are not supported")


@dataclass(slots=True)
class PreparedSummaries:
    """Validated cached/generated summaries for one render pass."""

    generated: int
    by_symbol_id: dict[str, str]


def provider_from_config(config: dict[str, object]) -> SummaryProvider:
    summaries = config["summaries"] if isinstance(config["summaries"], dict) else {}
    if not summaries.get("enabled", True):
        return DisabledSummaryProvider()
    provider = str(summaries.get("provider", "local"))
    if provider == "local":
        return LocalSummaryProvider()
    return RemoteSummaryProvider(
        provider, bool(summaries.get("allow_source_code_upload", False))
    )


def load_summary_cache(repo_root: Path) -> dict[str, dict[str, str]]:
    path = repo_root / CACHE_PATH
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_summary_cache(repo_root: Path, cache: dict[str, dict[str, str]]) -> None:
    path = repo_root / CACHE_PATH
    ensure_parent(path)
    path.write_text(
        json.dumps(cache, indent=2, sort_keys=True) + "\n", encoding="utf-8"
    )


def prune_summary_cache(repo_root: Path, live_symbol_ids: set[str]) -> int:
    """Remove cache entries for dead symbol IDs; return the count removed (no file: no-op)."""
    path = repo_root / CACHE_PATH
    if not path.is_file():
        return 0
    cache = load_summary_cache(repo_root)
    if not cache:
        return 0
    stale = [key for key in cache if key not in live_symbol_ids]
    if not stale:
        return 0
    for key in stale:
        del cache[key]
    save_summary_cache(repo_root, cache)
    return len(stale)


def generate_summaries(
    parsed_modules: list[ParsedModule],
    repo_root: Path,
    config: dict[str, object],
    *,
    symbol_id: str | None = None,
) -> int:
    if isinstance(provider_from_config(config), DisabledSummaryProvider):
        return 0
    prepared = prepare_summaries(
        parsed_modules,
        repo_root,
        config,
        generate_missing=True,
        write_summary_docs=True,
        symbol_id=symbol_id,
    )
    output_dir = repo_root / str(config["generation"]["output_dir"])  # type: ignore[index]
    commit = repo_commit(repo_root)
    for parsed in parsed_modules:
        for symbol in parsed.symbols:
            if symbol_id and symbol.symbol_id != symbol_id:
                continue
            summary = prepared.by_symbol_id.get(symbol.symbol_id)
            if summary is None:
                continue
            write_symbol_doc(
                symbol, output_dir, commit, repo_root.name, summary, repo_root
            )
    return prepared.generated


def prepare_summaries(
    parsed_modules: list[ParsedModule],
    repo_root: Path,
    config: dict[str, object],
    *,
    generate_missing: bool,
    write_summary_docs: bool,
    symbol_id: str | None = None,
) -> PreparedSummaries:
    """Return source-hash-valid summaries (cached ones even when generation is disabled)."""

    provider = provider_from_config(config)
    can_generate = generate_missing and not isinstance(
        provider, DisabledSummaryProvider
    )
    output_dir = repo_root / str(config["generation"]["output_dir"])  # type: ignore[index]
    cache = load_summary_cache(repo_root)
    summaries: dict[str, str] = {}
    generated = 0
    cache_changed = False

    for parsed in parsed_modules:
        for symbol in parsed.symbols:
            source_hash = sha256_text(read_source(symbol.span, repo_root))
            entry = cache.get(symbol.symbol_id)
            summary: str | None = None
            if entry and entry.get("source_hash") == source_hash:
                cached_summary = entry.get("summary")
                if isinstance(cached_summary, str):
                    summary = cached_summary
            elif can_generate and (symbol_id is None or symbol.symbol_id == symbol_id):
                summary = provider.summarize_symbol(symbol)
                if summary is not None:
                    cache[symbol.symbol_id] = {
                        "source_hash": source_hash,
                        "summary": summary,
                        "summary_hash": sha256_text(summary),
                    }
                    generated += 1
                    cache_changed = True
            if summary is None:
                continue
            summaries[symbol.symbol_id] = summary
            if write_summary_docs and (
                symbol_id is None or symbol.symbol_id == symbol_id
            ):
                write_summary_doc(symbol, summary, output_dir, source_hash)

    if cache_changed:
        save_summary_cache(repo_root, cache)
    return PreparedSummaries(generated=generated, by_symbol_id=summaries)


# Noun for the `class` kind per language; unlisted languages use "class".
_CLASS_NOUN_BY_LANGUAGE = {
    "rust": "struct",
    "julia": "struct",
}


def local_symbol_summary(symbol: Symbol) -> str:
    if symbol.kind == "class":
        noun = _CLASS_NOUN_BY_LANGUAGE.get(symbol.language.value, "class")
        action = f"defines a {noun}"
    else:
        action = {
            "function": "defines a function",
            "method": "defines a method",
            "constant": "defines a top-level constant",
            "module": "defines a module",
        }.get(symbol.kind, "defines a symbol")
    doc = f" {symbol.docstring.strip()}" if symbol.docstring else ""
    calls = ", ".join(symbol.calls[:5]) if symbol.calls else "no detected calls"
    return (
        f"`{symbol.qualname}` {action} in `{symbol.path}` at lines "
        f"{symbol.start_line}-{symbol.end_line}.{doc}\n\n"
        f"Inputs and outputs are inferred from the signature when available. "
        f"Important dependencies/calls: {calls}. This generated summary is a retrieval aid; "
        "use the source citation as the authority."
    )


def write_summary_doc(
    symbol: Symbol, summary: str, output_dir: Path, source_hash: str
) -> Path:
    path = output_dir / "summaries" / f"{safe_doc_name(symbol.symbol_id)}.summary.md"
    ensure_parent(path)
    path.write_text(
        "\n".join(
            [
                "---",
                "doc_type: summary",
                f"path: {symbol.path}",
                f"symbol_id: {symbol.symbol_id}",
                f"source_hash: {source_hash}",
                "---",
                f"# Summary: {symbol.symbol_id}",
                summary,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path

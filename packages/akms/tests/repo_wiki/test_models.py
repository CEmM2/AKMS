import pytest

from akms.repo_wiki.models import Language, SourceFile, SourceSpan, Symbol


def test_core_models_round_trip_minimal_fields():
    source = SourceFile("src/app.py", "/repo/src/app.py", "python", 10, "sha256:abc")
    assert SourceFile.from_dict(source.to_dict()).path == "src/app.py"
    symbol = Symbol(
        symbol_id="src.app.main",
        path="src/app.py",
        module="src.app",
        name="main",
        qualname="main",
        kind="function",
        parent_id=None,
        start_line=1,
        end_line=2,
        signature="def main()",
        docstring=None,
        span=SourceSpan(path="src/app.py", start_line=1, end_line=2),
    )
    assert Symbol.from_dict(symbol.to_dict()).symbol_id == "src.app.main"


def _symbol(**overrides: object) -> Symbol:
    base: dict[str, object] = dict(
        symbol_id="m.s",
        path="m.py",
        module="m",
        name="s",
        qualname="s",
        kind="function",
        parent_id=None,
        start_line=1,
        end_line=2,
        signature=None,
        docstring=None,
        span=SourceSpan(path="m.py", start_line=1, end_line=2),
    )
    base.update(overrides)
    return Symbol(**base)  # type: ignore[arg-type]


def test_symbol_to_dict_omits_empty_metadata():
    """Empty metadata must not appear in to_dict output (byte-identity for Python)."""
    assert "metadata" not in _symbol().to_dict()


def test_symbol_to_dict_includes_non_empty_metadata():
    """Non-empty metadata is emitted and round-trips through from_dict."""
    sym = _symbol(metadata={"visibility": "public"})
    d = sym.to_dict()
    assert d["metadata"] == {"visibility": "public"}
    assert Symbol.from_dict(d).metadata == {"visibility": "public"}


def test_symbol_from_dict_defaults_metadata_when_absent():
    """Legacy payloads without a metadata key load with empty metadata."""
    d = _symbol().to_dict()
    assert "metadata" not in d
    assert Symbol.from_dict(d).metadata == {}


def test_symbol_requires_a_source_span():
    """A symbol cannot be constructed without a span."""
    with pytest.raises(TypeError):
        Symbol(  # type: ignore[call-arg]
            symbol_id="m.s",
            path="m.py",
            module="m",
            name="s",
            qualname="s",
            kind="function",
            parent_id=None,
            start_line=1,
            end_line=2,
            signature=None,
            docstring=None,
        )


def test_symbol_round_trip_preserves_span_and_relations():
    """to_dict emits the span (not source text) and from_dict restores an equal symbol."""
    symbol = _symbol(
        symbol_id="src.app.main",
        path="src/app.py",
        start_line=3,
        end_line=7,
        span=SourceSpan(path="src/app.py", start_line=3, end_line=7),
        decorators=["staticmethod"],
        imports=["os"],
        calls=["helper"],
    )
    payload = symbol.to_dict()
    assert payload["span"] == {"path": "src/app.py", "start_line": 3, "end_line": 7}
    assert "source" not in payload
    assert "source_hash" not in payload
    assert Symbol.from_dict(payload) == symbol


def test_symbol_language_round_trips_as_string():
    """The language serialises to its string value and loads back as the enum member."""
    payload = _symbol(language=Language.PYTHON).to_dict()
    assert payload["language"] == "python"
    assert Symbol.from_dict(payload).language is Language.PYTHON

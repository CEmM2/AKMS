"""Language-qualified symbol id construction."""

from akms.repo_wiki.models import Language
from akms.repo_wiki.symbol_ids import build_symbol_id


def test_build_symbol_id_format_python():
    """build_symbol_id produces correct format for Python."""
    result = build_symbol_id(Language.PYTHON, "src/foo.py", "Bar.baz")
    assert result == "python:src/foo.py::Bar.baz"


def test_build_symbol_id_nested_qualname():
    """build_symbol_id handles nested qualnames with dots."""
    assert (
        build_symbol_id(Language.PYTHON, "pkg/mod.py", "Outer.Inner.method")
        == "python:pkg/mod.py::Outer.Inner.method"
    )
    assert (
        build_symbol_id(Language.PYTHON, "pkg/mod.py", "Child.run.nested")
        == "python:pkg/mod.py::Child.run.nested"
    )


def test_build_symbol_id_unusual_relpath():
    """build_symbol_id handles unusual relpaths (underscores, hyphens, deep nesting)."""
    assert (
        build_symbol_id(
            Language.PYTHON, "src/my_pkg/sub-dir/utils.py", "MyClass.my_method"
        )
        == "python:src/my_pkg/sub-dir/utils.py::MyClass.my_method"
    )
    # Windows-style backslashes are normalised to forward slashes
    assert (
        build_symbol_id(Language.PYTHON, "src\\repo2md\\models.py", "Symbol.to_dict")
        == "python:src/repo2md/models.py::Symbol.to_dict"
    )

"""Default local knowledge directory: .knowledge, with a legacy fallback."""

from pathlib import Path

from akms.layout import local_knowledge_dir


def test_absent_directory_defaults_to_dot_knowledge(tmp_path: Path) -> None:
    assert local_knowledge_dir(tmp_path) == tmp_path / ".knowledge"


def test_legacy_directory_is_kept_when_dot_knowledge_is_absent(tmp_path: Path) -> None:
    (tmp_path / "knowledge").mkdir()
    assert local_knowledge_dir(tmp_path) == tmp_path / "knowledge"


def test_dot_knowledge_wins_when_both_directories_exist(tmp_path: Path) -> None:
    (tmp_path / "knowledge").mkdir()
    (tmp_path / ".knowledge").mkdir()
    assert local_knowledge_dir(tmp_path) == tmp_path / ".knowledge"


def test_a_file_is_not_treated_as_the_knowledge_directory(tmp_path: Path) -> None:
    (tmp_path / "knowledge").write_text("not a directory")
    (tmp_path / ".knowledge").write_text("not a directory")
    assert local_knowledge_dir(tmp_path) == tmp_path / ".knowledge"

"""Configuration loading and initialization."""

from __future__ import annotations

from copy import deepcopy
from pathlib import Path

from akms.repo_wiki.simple_yaml import dump_yaml, load_yaml

CONFIG_DIR = ".repo_wiki"
CONFIG_FILE = "config.yaml"
SPEC_FILE = "SPEC.md"


def default_config(repo_root: Path | None = None) -> dict[str, object]:
    repo_name = (repo_root or Path.cwd()).resolve().name
    return {
        "flows": default_flows_config(),
        "generation": {
            "generate_module_docs": True,
            "generate_repo_map": True,
            "generate_symbol_docs": True,
            "include_docstrings": True,
            "include_full_code": True,
            "include_imports": True,
            "include_line_numbers": True,
            "include_signatures": True,
            "output_dir": ".repo_wiki/generated",
        },
        "index": {
            "backend": "qmd",
            "bm25": True,
            "chunking": {
                "max_chunk_chars": 8000,
                "mode": "symbol",
                "overlap_chars": 500,
            },
            "hybrid_search": True,
            "rerank": True,
            "vectors": True,
        },
        "languages": {"python": {"enabled": True}},
        "repo": {"default_branch": "main", "name": repo_name, "root": "."},
        "retrieval": {
            "expand_callees": True,
            "expand_callers": True,
            "expand_children": True,
            "expand_heuristic_edges": True,
            "expand_parent": True,
            "expand_siblings": False,
            "include_tests": True,
            "top_k_initial": 30,
            "top_k_reranked": 8,
        },
        "scanner": {
            "exclude": [
                ".git/**",
                ".repo_wiki/generated/**",
                ".repo_wiki/index/**",
                ".venv/**",
                "venv/**",
                "env/**",
                "__pycache__/**",
                ".mypy_cache/**",
                ".pytest_cache/**",
                "node_modules/**",
                "dist/**",
                "build/**",
                "*.egg-info/**",
                "data/**",
                "outputs/**",
                "checkpoints/**",
                "wandb/**",
                ".env",
                ".env.*",
                "*.env",
                "*.pem",
                "*.key",
                "*.p12",
                "*.pfx",
                "*_secret",
                "*_secret.*",
                "*_secrets",
                "*_secrets.*",
                "*.secret",
                "*.secrets",
                "secrets.yaml",
                "secrets.yml",
                "secrets.json",
                "credentials",
                "credentials.*",
                "credentials.json",
                "credentials.yaml",
                "credentials.yml",
                "id_rsa",
                "id_ed25519",
                "id_dsa",
                "id_ecdsa",
                ".netrc",
                "*.netrc",
            ],
            "include": ["**/*.py", "**/*.md", "**/*.yaml", "**/*.yml", "**/*.toml"],
            "max_file_size_kb": 512,
            "respect_gitignore": True,
        },
        "summaries": {
            "allow_source_code_upload": False,
            "cache": True,
            "enabled": True,
            "max_symbol_chars": 12000,
            "model": None,
            "provider": "local",
            "regenerate_on_code_change": True,
        },
    }


def default_flows_config() -> dict[str, object]:
    """Defaults for the ``flows:`` section (execution flows; see ``akms.repo_wiki.flows``)."""
    return {
        "cli_decorators": ["*.command", "*.group"],
        "enabled": True,
        "entries": {
            "cli": True,
            "console_scripts": True,
            "roots": True,
            "scripts": True,
            "tests": False,
        },
        "include_heuristic": False,
        "max_depth": 6,
        "max_fanout": 12,
        "max_flows": 1000,
        "max_steps": 60,
    }


FLOW_ENTRY_RULES = ("cli", "console_scripts", "roots", "scripts", "tests")


def deep_merge(
    base: dict[str, object], updates: dict[str, object]
) -> dict[str, object]:
    result = deepcopy(base)
    for key, value in updates.items():
        if isinstance(value, dict) and isinstance(result.get(key), dict):
            result[key] = deep_merge(result[key], value)  # type: ignore[arg-type]
        else:
            result[key] = value
    return result


def config_path(repo_root: Path) -> Path:
    return repo_root / CONFIG_DIR / CONFIG_FILE


def load_config(repo_root: Path | None = None) -> dict[str, object]:
    root = (repo_root or Path.cwd()).resolve()
    path = config_path(root)
    config = default_config(root)
    if path.exists():
        config = deep_merge(config, load_yaml(path.read_text(encoding="utf-8")))
    validate_config(config)
    return config


def validate_config(config: dict[str, object]) -> None:
    scanner = _mapping(config, "scanner")
    generation = _mapping(config, "generation")
    summaries = _mapping(config, "summaries")
    max_size = scanner["max_file_size_kb"]
    if not isinstance(max_size, (int, float, str)) or int(max_size) <= 0:
        raise ValueError("scanner.max_file_size_kb must be positive")
    if not generation.get("output_dir"):
        raise ValueError("generation.output_dir is required")
    if summaries.get("provider") != "local" and not summaries.get(
        "allow_source_code_upload"
    ):
        raise ValueError(
            "remote summary providers require allow_source_code_upload: true"
        )
    if "flows" in config:
        validate_flows_config(_mapping(config, "flows"))


def validate_flows_config(flows: dict[str, object]) -> None:
    """Reject a ``flows:`` section with unknown keys or values of the wrong type."""
    known = set(default_flows_config())
    unknown = sorted(set(flows) - known)
    if unknown:
        raise ValueError(f"flows: unknown key(s) {', '.join(unknown)}")
    for key in ("enabled", "include_heuristic"):
        if key in flows and not isinstance(flows[key], bool):
            raise ValueError(f"flows.{key} must be true or false")
    for key in ("max_depth", "max_fanout", "max_flows", "max_steps"):
        value = flows.get(key, 1)
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"flows.{key} must be a positive integer")
    entries = flows.get("entries", {})
    if not isinstance(entries, dict):
        raise ValueError("flows.entries must be a mapping")
    for key, value in entries.items():
        if key not in FLOW_ENTRY_RULES:
            raise ValueError(
                f"flows.entries: unknown rule {key!r} "
                f"(known: {', '.join(FLOW_ENTRY_RULES)})"
            )
        if not isinstance(value, bool):
            raise ValueError(f"flows.entries.{key} must be true or false")
    patterns = flows.get("cli_decorators", [])
    if not isinstance(patterns, list) or not all(
        isinstance(item, str) and item for item in patterns
    ):
        raise ValueError("flows.cli_decorators must be a list of patterns")


def _mapping(config: dict[str, object], key: str) -> dict[str, object]:
    value = config.get(key)
    if not isinstance(value, dict):
        raise ValueError(f"{key} must be a mapping")
    return value


def init_repo_wiki(repo_root: Path | None = None) -> list[Path]:
    root = (repo_root or Path.cwd()).resolve()
    wiki = root / CONFIG_DIR
    overlays = wiki / "overlays"
    created: list[Path] = []
    wiki.mkdir(exist_ok=True)
    overlays.mkdir(exist_ok=True)
    if overlays not in created:
        created.append(overlays)
    cfg = config_path(root)
    if not cfg.exists():
        cfg.write_text(dump_yaml(default_config(root)), encoding="utf-8")
        created.append(cfg)
    spec = wiki / SPEC_FILE
    if not spec.exists():
        spec.write_text(default_spec(root.name), encoding="utf-8")
        created.append(spec)
    return created


def default_spec(repo_name: str) -> str:
    return (
        f"# Repository Wiki Specification: {repo_name}\n\n"
        "This directory is managed by `repo-wiki`.\n\n"
        "- Generated files live under `.repo_wiki/generated/` and are disposable.\n"
        "- Human-authored notes belong under `.repo_wiki/overlays/`.\n"
        "- Source files remain canonical for answers and citations.\n"
        "- Local/private operation is the default.\n"
    )

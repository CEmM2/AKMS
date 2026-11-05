"""Configuration loading and initialization."""

from __future__ import annotations

from collections.abc import Mapping
from copy import deepcopy
from pathlib import Path, PurePosixPath

from akms.repo_wiki.simple_yaml import dump_yaml, load_yaml

CONFIG_DIR = ".repo_wiki"
CONFIG_FILE = "config.yaml"
SPEC_FILE = "SPEC.md"

# Version-control and repo-wiki state. Always applied; no configuration key removes
# them. None of it is source, and generated pages, the index and the caches hold
# copies of source. ``.git`` matches at any depth, so it also covers the ``.git``
# file of a worktree or submodule and a nested repository's ``.git`` directory.
# ``.repo_wiki/**`` covers everything repo-wiki keeps there (config.yaml, SPEC.md,
# generated/, index/, ir_cache/, cache/, locks/, hooks/, manifest.json,
# build_errors.json) and the overlays, which the index reads directly rather than
# through the scanner. ``.repo_wiki/generated/**`` and ``.repo_wiki/index/**``
# are subsumed but kept, so the set holds every pattern older versions of
# ``init`` wrote. The export lock files sit next to an export's output tree.
TOOL_STATE_EXCLUDE_PATTERNS: tuple[str, ...] = (
    ".git",
    ".git/**",
    ".repo_wiki/**",
    ".repo_wiki/generated/**",
    ".repo_wiki/index/**",
    ".repo2md-export.lock",
    ".repo2md-export-*.lock",
)

# Ordinary default excludes: environments, caches, build and data output.
# ``scanner.exclude`` adds to these; ``scanner.use_default_excludes: false`` drops them.
DEFAULT_EXCLUDE_PATTERNS: tuple[str, ...] = (
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
)

# Secret and credential files. The scanner always applies these, also against the
# file name at any depth; no configuration key removes them.
SECRET_EXCLUDE_PATTERNS: tuple[str, ...] = (
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
)

# Slash-free fixed patterns, also matched against the file name at any depth.
PROTECTED_NAME_PATTERNS: tuple[str, ...] = tuple(
    pattern
    for pattern in (*TOOL_STATE_EXCLUDE_PATTERNS, *SECRET_EXCLUDE_PATTERNS)
    if "/" not in pattern
)

# ``scanner.include`` replaces this list: narrowing what is scanned is not a safety issue.
DEFAULT_INCLUDE_PATTERNS: tuple[str, ...] = (
    "**/*.py",
    "**/*.md",
    "**/*.yaml",
    "**/*.yml",
    "**/*.toml",
)

CONFIG_HEADER = (
    "# repo-wiki configuration, merged over the built-in defaults key by key.\n"
    "# scanner.exclude adds patterns to the built-in default excludes\n"
    "# (environments, caches, build and data output); it does not replace them.\n"
    "# scanner.use_default_excludes: false drops those defaults. Version-control\n"
    "# and repo-wiki state (.git, .repo_wiki/) and secret and credential patterns\n"
    "# (.env files, keys, certificates, *_secret, credentials, ...) are always\n"
    "# excluded and cannot be removed by configuration.\n"
    "# scanner.include replaces the default include list.\n"
)


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
        # No ``exclude`` key: user patterns are additions to DEFAULT_EXCLUDE_PATTERNS.
        # Leaving it out also keeps an older repo-wiki on its built-in list.
        "scanner": {
            "include": list(DEFAULT_INCLUDE_PATTERNS),
            "max_file_size_kb": 512,
            "respect_gitignore": True,
            "use_default_excludes": True,
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


def effective_excludes(
    config: Mapping[str, object], *, tool_state: bool = True
) -> list[str]:
    """The exclude patterns the scanner applies, in a stable order.

    The tool-state set comes first, with the configured ``generation.output_dir``,
    then the ordinary defaults (unless ``scanner.use_default_excludes`` is
    ``false``), then the secret set, then the ``scanner.exclude`` entries. A
    duplicate keeps its first position, so a config that still lists the
    copied-out list older versions of ``init`` wrote adds nothing.
    ``tool_state=False`` leaves the tool-state set out, for the index's own
    walk of ``.repo_wiki/overlays/``.
    """

    scanner = config.get("scanner")
    if not isinstance(scanner, Mapping):
        scanner = {}
    patterns: list[str] = []
    if tool_state:
        patterns.extend(TOOL_STATE_EXCLUDE_PATTERNS)
        output_dir = _generated_dir_pattern(config)
        if output_dir is not None:
            patterns.append(output_dir)
    # Only an explicit ``false`` drops the ordinary defaults.
    if scanner.get("use_default_excludes", True) is not False:
        patterns.extend(DEFAULT_EXCLUDE_PATTERNS)
    patterns.extend(SECRET_EXCLUDE_PATTERNS)
    patterns.extend(_pattern_list(scanner, "exclude"))
    return list(dict.fromkeys(patterns))


def _generated_dir_pattern(config: Mapping[str, object]) -> str | None:
    """``<generation.output_dir>/**`` for a repository-relative output directory."""
    generation = config.get("generation")
    if not isinstance(generation, Mapping):
        return None
    raw = generation.get("output_dir")
    if not isinstance(raw, str) or not raw.strip():
        return None
    path = PurePosixPath(raw.strip().replace("\\", "/"))
    if path.is_absolute() or ".." in path.parts or str(path) in {"", "."}:
        return None
    return f"{path.as_posix()}/**"


def _pattern_list(scanner: Mapping[str, object], key: str) -> list[str]:
    value = scanner.get(key, [])
    # A bare ``key:`` with no items reads as an empty mapping in the YAML subset.
    if value is None or value == {}:
        return []
    if not isinstance(value, (list, tuple)):
        raise ValueError(
            f"scanner.{key} must be a list of patterns, one '- pattern' per line"
        )
    return [str(item) for item in value]


def validate_config(config: dict[str, object]) -> None:
    scanner = _mapping(config, "scanner")
    generation = _mapping(config, "generation")
    summaries = _mapping(config, "summaries")
    max_size = scanner["max_file_size_kb"]
    if not isinstance(max_size, (int, float, str)) or int(max_size) <= 0:
        raise ValueError("scanner.max_file_size_kb must be positive")
    for key in ("exclude", "include"):
        _pattern_list(scanner, key)
    if not isinstance(scanner.get("use_default_excludes", True), bool):
        raise ValueError("scanner.use_default_excludes must be true or false")
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
        cfg.write_text(
            CONFIG_HEADER + dump_yaml(default_config(root)), encoding="utf-8"
        )
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

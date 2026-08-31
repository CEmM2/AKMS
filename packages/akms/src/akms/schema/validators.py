"""YAML frontmatter parsers and validators for AKMS v2 schemas.

All parse functions validate schema version and return typed Pydantic models.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

import frontmatter
import yaml
from pydantic import ValidationError

from akms import AKMS_SCHEMA_VERSION
from akms.schema.errors import SchemaValidationError, SchemaVersionError
from akms.schema.models import (
    EXPERIENTIAL_FIELDS,
    AgentMemory,
    CodeMirrorNodeFrontmatter,
    GlobalNodeFrontmatter,
    LocalNodeFrontmatter,
    LocalStateOverlay,
    PCD,
    PropagationConfig,
)

logger = logging.getLogger(__name__)


def _check_schema_version(
    data: dict[str, Any], path: str | None = None
) -> None:
    """Validate akms_schema field matches expected version."""
    version = data.get("akms_schema")
    if version is None:
        raise SchemaValidationError("Missing required field 'akms_schema'", path)
    if version != AKMS_SCHEMA_VERSION:
        raise SchemaVersionError(found=str(version), path=path)


def _check_no_experiential_fields(
    data: dict[str, Any], path: str | None = None
) -> None:
    """Ensure global nodes don't contain experiential fields."""
    present = EXPERIENTIAL_FIELDS & set(data.keys())
    if present:
        raise SchemaValidationError(
            f"Global node contains experiential fields (must be in "
            f"local_state.yaml, not node frontmatter): {sorted(present)}",
            path,
        )


def _load_frontmatter(path: str | Path) -> tuple[dict[str, Any], str]:
    """Load YAML frontmatter and content from a markdown file.

    Returns (frontmatter_dict, markdown_content).
    """
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    post = frontmatter.load(str(path))
    return dict(post.metadata), post.content


def _load_yaml(path: str | Path) -> dict[str, Any]:
    """Load a pure YAML file."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")

    with open(path) as f:
        data = yaml.safe_load(f)

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise SchemaValidationError(
            f"Expected YAML mapping, got {type(data).__name__}", str(path)
        )
    return data


# ──────────────────────────────────────────────────────────────────────
#  Node Frontmatter Parsers
# ──────────────────────────────────────────────────────────────────────


def parse_node_frontmatter(
    path: str | Path,
    *,
    is_local: bool = False,
    is_code_mirror: bool = False,
) -> GlobalNodeFrontmatter | LocalNodeFrontmatter | CodeMirrorNodeFrontmatter:
    """Parse and validate a knowledge node's YAML frontmatter.

    Args:
        path: Path to the .md node file.
        is_local: If True, validates as a local node (allows agent source).
        is_code_mirror: If True, validates as a code-mirror node.

    Returns:
        Validated Pydantic model.

    Raises:
        SchemaVersionError: If akms_schema doesn't match.
        SchemaValidationError: If required fields are missing or invalid.
        FileNotFoundError: If file doesn't exist.
    """
    path_str = str(path)
    data, _content = _load_frontmatter(path)
    _check_schema_version(data, path_str)

    try:
        if is_code_mirror:
            return CodeMirrorNodeFrontmatter(**data)
        elif is_local:
            return LocalNodeFrontmatter(**data)
        else:
            # Global node: reject experiential fields
            _check_no_experiential_fields(data, path_str)
            return GlobalNodeFrontmatter(**data)
    except ValidationError as e:
        raise SchemaValidationError(str(e), path_str) from e


def parse_node_frontmatter_from_dict(
    data: dict[str, Any],
    *,
    is_local: bool = False,
    is_code_mirror: bool = False,
    path: str | None = None,
) -> GlobalNodeFrontmatter | LocalNodeFrontmatter | CodeMirrorNodeFrontmatter:
    """Parse and validate frontmatter from a pre-loaded dict.

    Useful when frontmatter has already been extracted (e.g., during build).
    """
    _check_schema_version(data, path)

    try:
        if is_code_mirror:
            return CodeMirrorNodeFrontmatter(**data)
        elif is_local:
            return LocalNodeFrontmatter(**data)
        else:
            _check_no_experiential_fields(data, path)
            return GlobalNodeFrontmatter(**data)
    except ValidationError as e:
        raise SchemaValidationError(str(e), path) from e


# ──────────────────────────────────────────────────────────────────────
#  Local State Overlay
# ──────────────────────────────────────────────────────────────────────


def parse_local_state(path: str | Path) -> LocalStateOverlay:
    """Parse and validate local_state.yaml.

    Returns:
        Validated LocalStateOverlay model.
    """
    path_str = str(path)
    data = _load_yaml(path)

    if not data:
        # Empty file → return default overlay
        return LocalStateOverlay()

    _check_schema_version(data, path_str)

    try:
        return LocalStateOverlay(**data)
    except ValidationError as e:
        raise SchemaValidationError(str(e), path_str) from e


# ──────────────────────────────────────────────────────────────────────
#  AgentMemory
# ──────────────────────────────────────────────────────────────────────


def parse_agent_memory(path: str | Path) -> AgentMemory:
    """Parse and validate a per-task AgentMemory file.

    Returns:
        Validated AgentMemory model.
    """
    path_str = str(path)
    data, _content = _load_frontmatter(path)
    _check_schema_version(data, path_str)

    try:
        return AgentMemory(**data)
    except ValidationError as e:
        raise SchemaValidationError(str(e), path_str) from e




def parse_pcd(path: str | Path) -> PCD:
    """Parse and validate a Phase Completion Document.

    Returns:
        Validated PCD model with zone extraction methods.
    """
    path_str = str(path)
    data, _content = _load_frontmatter(path)
    _check_schema_version(data, path_str)

    try:
        return PCD(**data)
    except ValidationError as e:
        raise SchemaValidationError(str(e), path_str) from e


# ──────────────────────────────────────────────────────────────────────
#  Propagation Config
# ──────────────────────────────────────────────────────────────────────


def parse_propagation_config(path: str | Path) -> PropagationConfig:
    """Parse and validate propagation_config.yaml.

    Returns:
        Validated PropagationConfig model.
    """
    path_str = str(path)
    data = _load_yaml(path)

    if not data:
        return PropagationConfig()

    _check_schema_version(data, path_str)

    try:
        return PropagationConfig(**data)
    except ValidationError as e:
        raise SchemaValidationError(str(e), path_str) from e

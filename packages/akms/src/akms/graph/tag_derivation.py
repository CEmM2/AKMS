"""tag_derivation.py — Hybrid Tag Derivation Engine (§4 of schema spec).

Derives ``akms_tags`` for task JSONs when not explicitly set by the developer.
Two strategies, run in sequence, results unioned:

1. **Scope-based**: Match task ``scope`` file paths against code-mirror node
   ``source_file`` fields and global node ``content_ref`` fields. Extract the
   owning node's tags.

2. **Text-based**: Concatenate ``title + objective + implementation_steps``,
   then match against node titles (whole-word) and node tags (substring,
   min ``min_tag_length`` chars).

No LLM calls. Pure deterministic string matching.
"""

from __future__ import annotations

import logging
import re

import networkx as nx

from akms.schema.models import PropagationConfig, TagDerivationConfig, TitleMatch
from akms.telemetry import traced

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Scope-Based Tag Derivation
# ═══════════════════════════════════════════════════════════════════════


def _derive_tags_from_scope(
    G: nx.DiGraph,
    scope: list[str],
) -> set[str]:
    """Match task scope paths against graph node fields.

    For each scope path:
    - Check code-mirror nodes whose ``source_file`` matches or is a prefix
    - Check all nodes whose ``content_ref`` matches or is a prefix
    - Collect tags from matching nodes

    Args:
        G: Compiled knowledge graph.
        scope: List of file paths from the task JSON.

    Returns:
        Set of derived tags.
    """
    tags: set[str] = set()

    if not scope:
        return tags

    for node_id, data in G.nodes(data=True):
        node_tags = data.get("tags", [])
        if not node_tags:
            continue

        source_file = data.get("source_file", "")
        content_ref = data.get("content_ref", "")

        for scope_path in scope:
            # Normalize paths for comparison
            scope_norm = scope_path.replace("\\", "/")

            # Check source_file match (code-mirror nodes)
            if source_file:
                sf_norm = source_file.replace("\\", "/")
                if (
                    sf_norm == scope_norm
                    or scope_norm.startswith(sf_norm)
                    or sf_norm.startswith(scope_norm)
                ):
                    tags.update(node_tags)
                    break

            # Check content_ref match (global/local nodes)
            if content_ref:
                cr_norm = content_ref.replace("\\", "/")
                if (
                    cr_norm == scope_norm
                    or scope_norm.endswith(cr_norm)
                    or cr_norm.endswith(scope_norm)
                ):
                    tags.update(node_tags)
                    break

    return tags


# ═══════════════════════════════════════════════════════════════════════
#  Text-Based Tag Derivation
# ═══════════════════════════════════════════════════════════════════════


def _build_text_corpus(task: dict) -> str:
    """Concatenate task text fields into a searchable corpus.

    Concatenates: title + objective + implementation_steps (joined).
    All lowercased for case-insensitive matching.
    """
    parts = []

    title = task.get("title", "")
    if title:
        parts.append(title)

    objective = task.get("objective", "")
    if objective:
        parts.append(objective)

    steps = task.get("implementation_steps", [])
    if isinstance(steps, list):
        parts.extend(str(s) for s in steps)
    elif isinstance(steps, str):
        parts.append(steps)

    return " ".join(parts).lower()


def _derive_tags_from_text(
    G: nx.DiGraph,
    task: dict,
    config: TagDerivationConfig,
) -> set[str]:
    """Match task text against node titles and tags.

    Title matching: whole-word by default (configurable via config.title_match).
    Tag matching: substring, minimum ``min_tag_length`` chars.

    Args:
        G: Compiled knowledge graph.
        task: Task JSON dict.
        config: Tag derivation configuration.

    Returns:
        Set of derived tags.
    """
    tags: set[str] = set()
    corpus = _build_text_corpus(task)

    if not corpus:
        return tags

    min_len = config.min_tag_length

    for node_id, data in G.nodes(data=True):
        node_tags = data.get("tags", [])
        node_title = data.get("title", "")

        # Title matching
        if node_title:
            title_lower = node_title.lower()
            if config.title_match == TitleMatch.WHOLE_WORD:
                # Match any word from the title (3+ chars) in the corpus
                title_words = re.findall(r"[a-z0-9][-a-z0-9_]*[a-z0-9]", title_lower)
                for word in title_words:
                    if len(word) >= 3 and re.search(
                        r"\b" + re.escape(word) + r"\b", corpus
                    ):
                        tags.update(node_tags)
                        break
            else:
                # Substring match
                if title_lower in corpus:
                    tags.update(node_tags)

        # Tag matching (substring, min length)
        for tag in node_tags:
            if len(tag) < min_len:
                continue
            tag_lower = tag.lower()
            if tag_lower in corpus:
                tags.add(tag)

    return tags


# ═══════════════════════════════════════════════════════════════════════
#  Main Entry Point
# ═══════════════════════════════════════════════════════════════════════


@traced("akms.derive_tags")
def derive_tags(
    G: nx.DiGraph,
    task: dict,
    config: PropagationConfig | None = None,
) -> list[str]:
    """Derive AKMS tags for a task using hybrid (scope + text) derivation.

    If the task already has non-empty ``akms_tags``, returns them unchanged
    (explicit tags from developer take precedence).

    Args:
        G: Compiled knowledge graph.
        task: Task JSON dict. Expected keys:
            - ``akms_tags`` (list[str], may be empty)
            - ``scope`` (list[str], file paths)
            - ``title`` (str)
            - ``objective`` (str)
            - ``implementation_steps`` (list[str])
        config: PropagationConfig (uses ``tag_derivation`` section).

    Returns:
        Sorted list of derived tags.
    """
    if config is None:
        config = PropagationConfig()

    td_config = config.tag_derivation

    # Check for explicit tags
    existing = task.get("akms_tags", [])
    if existing:
        logger.debug("Task already has explicit akms_tags: %s", existing)
        return sorted(existing)

    # Strategy 1: scope-based
    scope = task.get("scope", [])
    scope_tags = _derive_tags_from_scope(G, scope)

    # Strategy 2: text-based
    text_tags = _derive_tags_from_text(G, task, td_config)

    all_tags = scope_tags | text_tags

    result = sorted(all_tags)

    if td_config.log_derived_tags:
        logger.info(
            "derive_tags: scope=%d text=%d total=%d tags=%s",
            len(scope_tags),
            len(text_tags),
            len(result),
            result,
        )

    return result


def fill_task_tags(
    G: nx.DiGraph,
    tasks: list[dict],
    config: PropagationConfig | None = None,
) -> list[dict]:
    """Derive and fill akms_tags for a list of tasks.

    Modifies tasks in-place and returns them. Only fills tags for tasks
    where ``akms_tags`` is empty or missing.

    Args:
        G: Compiled knowledge graph.
        tasks: List of task JSON dicts.
        config: PropagationConfig.

    Returns:
        The same list of tasks (modified in-place).
    """
    for task in tasks:
        derived = derive_tags(G, task, config)
        task["akms_tags"] = derived
    return tasks


# ═══════════════════════════════════════════════════════════════════════
#  Reviewer Seed Derivation
# ═══════════════════════════════════════════════════════════════════════


def derive_review_seeds(
    G: nx.DiGraph,
    files_modified: list[str],
    fallback_tags: list[str] | None = None,
) -> list[str]:
    """Seed tags for reviewer loadouts based on phase-branch changes.

    Walks ``files_modified`` (from ``git diff`` against the phase-parent
    branch) and collects tags from:
      - Code-mirror nodes whose ``source_file`` matches (intended primary
        entry point per FR-T03).
      - Concept nodes whose ``content_ref`` matches.

    When ``files_modified`` is empty (e.g. first phase, or the reviewer runs
    before any file change lands), fall back to ``fallback_tags`` — typically
    the union of completed-task ``akms_tags`` for this phase.

    The return value is a deterministically ordered list so downstream
    ``query_subgraph`` calls produce reproducible loadouts.
    """
    tags = _derive_tags_from_scope(G, list(files_modified or []))
    if not tags and fallback_tags:
        tags = {str(t) for t in fallback_tags if t}
    return sorted(tags)

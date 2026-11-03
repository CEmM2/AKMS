"""Subprocess mirror providers for ``repo-wiki export-akms``.

``repo2md`` runs a configured external ``repo-wiki`` command; ``builtin`` runs
the copy that ships in akms (``python -m akms.repo_wiki``). Both invoke the
exporter via an argv list only (``shell=False``) and never import it, so the
export contract, JSON result, timeout and lock behaviour are the same for both.

All failures (timeout, nonzero exit, malformed JSON, schema mismatch,
path escape, partial/incomplete output) raise ``MirrorProviderError``
before graph compilation.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

import frontmatter as fm

from akms.graph.mirror_provider import (
    MirrorProviderError,
    MirrorRequest,
    MirrorResult,
)
from akms.layout import local_knowledge_dir
from akms.schema.errors import SchemaValidationError, SchemaVersionError
from akms.schema.models import MirrorConfig
from akms.schema.validators import parse_node_frontmatter_from_dict

logger = logging.getLogger(__name__)

# The knowledge directory the external exporter writes under the output root.
# Code-mirror output must stay under ``<knowledge dir>/code-mirror``.
_DEFAULT_KNOWLEDGE_DIR = "knowledge"


class Repo2mdMirrorProvider:
    """External repo2md CLI provider — argv only, no Python import."""

    name = "repo2md"
    cli = "repo-wiki export-akms"

    def command(self, config: MirrorConfig) -> list[str]:
        """Argv prefix that runs the exporter."""
        return list(config.command)

    def knowledge_dir(self, output_root: Path) -> str | None:
        """Knowledge directory to request, or None for the exporter's default."""
        return None

    def strict_parse(self, config: MirrorConfig) -> bool:
        """Whether to pass ``--strict-parse``; the external exporter lacks the flag."""
        return False

    def generate(self, request: MirrorRequest, config: MirrorConfig) -> MirrorResult:
        repo_root = Path(request.repo_root).resolve()
        output_root = Path(request.output_root or repo_root).resolve()
        generated_at = request.generated_at or datetime.now(tz=timezone.utc)
        knowledge_dir = self.knowledge_dir(output_root)

        argv = build_repo2md_argv(
            config=config,
            command=self.command(config),
            knowledge_dir=knowledge_dir,
            strict_parse=self.strict_parse(config),
            provider=self.name,
            repo_root=repo_root,
            output_root=output_root,
            phase=request.phase,
            generated_at=generated_at,
            source_files=request.source_files,
            selection_mode=request.selection_mode,
            parent_branch=request.parent_branch,
            git_base=request.git_base,
            git_head=request.git_head,
            prune=request.prune,
            force_lock=request.force_lock,
        )
        raw = _run_subprocess(argv, config=config, cwd=repo_root, provider=self.name)
        export = _parse_export_json(raw, config=config, provider=self.name)
        mirrors = validate_repo2md_export(
            export,
            repo_root=repo_root,
            output_root=output_root,
            config=config,
            knowledge_dir=knowledge_dir or _DEFAULT_KNOWLEDGE_DIR,
            provider=self.name,
        )

        parse_skipped = _parse_skipped_paths(export)

        # Optional drift on Python sources after successful export.
        drift_warnings: list[dict[str, Any]] = []
        if request.drift_check:
            drift_warnings = _run_python_drift(
                repo_root=repo_root,
                source_files=_python_sources_from_export(
                    export, request.source_files, parse_skipped=parse_skipped
                ),
                llm_fn=request.llm_fn,
            )

        return MirrorResult(
            mirrors=mirrors,
            drift_warnings=drift_warnings,
            files_processed=len(export.get("written", []) or []),
            definitions_total=len(mirrors),
            provider=self.name,
            provider_metadata={
                "kind": "subprocess",
                "cli": self.cli,
                "command_basename": Path(argv[0]).name if argv else "",
                "export_schema_version": export.get("export_schema_version"),
                "phase": export.get("phase"),
                "written_count": len(export.get("written", []) or []),
                "removed_count": len(export.get("removed", []) or []),
                "skipped_count": len(export.get("skipped", []) or []),
                "error_count": len(export.get("errors", []) or []),
                "parse_skipped": parse_skipped,
            },
            errors=[],
            success=True,
            fallback_used=False,
        )


# ═══════════════════════════════════════════════════════════════════════
#  Argv construction (no shell)
# ═══════════════════════════════════════════════════════════════════════


def build_repo2md_argv(
    *,
    config: MirrorConfig,
    repo_root: Path,
    output_root: Path,
    phase: int,
    generated_at: datetime,
    source_files: list[str] | None = None,
    selection_mode: str = "changed",
    parent_branch: str = "main",
    git_base: str | None = None,
    git_head: str | None = None,
    prune: bool = False,
    force_lock: bool = False,
    command: list[str] | None = None,
    knowledge_dir: str | None = None,
    strict_parse: bool = False,
    provider: str = "repo2md",
) -> list[str]:
    """Build a complete argv list for ``repo-wiki export-akms``.

    Never joins into a shell string. Rejects empty/malformed command prefixes.
    ``command`` overrides ``config.command``; ``knowledge_dir`` adds
    ``--knowledge-dir`` and ``strict_parse`` adds ``--strict-parse``; only the
    built-in exporter understands either.
    """
    prefix = list(config.command) if command is None else command
    if not prefix or not all(isinstance(c, str) and c for c in prefix):
        raise MirrorProviderError(
            f"{provider} provider requires MirrorConfig.command as a non-empty argv list",
            provider=provider,
            code="invalid_command",
        )
    if phase < 1:
        raise MirrorProviderError(
            f"phase must be a positive integer, got {phase!r}",
            provider=provider,
            code="invalid_phase",
        )

    ts = _format_generated_at(generated_at)
    argv: list[str] = [
        *prefix,
        "--repo-root",
        str(repo_root),
        "export-akms",
        "--output",
        str(output_root),
        *(["--knowledge-dir", knowledge_dir] if knowledge_dir else []),
        *(["--strict-parse"] if strict_parse else []),
        "--phase",
        str(int(phase)),
        "--generated-at",
        ts,
        "--json",
    ]

    mode = (selection_mode or "changed").strip().lower()
    paths = list(source_files) if source_files else None
    effective_git_base = git_base
    effective_git_head = git_head

    if paths:
        for p in paths:
            if not isinstance(p, str) or not p.strip():
                raise MirrorProviderError(
                    f"Invalid source path in selection: {p!r}",
                    provider=provider,
                    code="invalid_path_selection",
                )
            # Reject shell metacharacters / absolute escapes early.
            if p.startswith("/") or (len(p) > 1 and p[1] == ":"):
                raise MirrorProviderError(
                    f"Source path must be repository-relative: {p!r}",
                    provider=provider,
                    code="absolute_path_selection",
                )
            argv.extend(["--path", p])
    elif mode == "full":
        argv.append("--full")
    elif mode in ("changed", "git"):
        base = effective_git_base or parent_branch or "main"
        argv.extend(["--git-base", base])
        if effective_git_head:
            argv.extend(["--git-head", effective_git_head])
    elif mode == "paths":
        raise MirrorProviderError(
            "selection_mode='paths' requires source_files",
            provider=provider,
            code="missing_path_selection",
        )
    else:
        raise MirrorProviderError(
            f"Unknown selection_mode {mode!r}",
            provider=provider,
            code="invalid_selection_mode",
        )

    if prune:
        argv.append("--prune")
    if force_lock:
        argv.append("--force-lock")

    return argv


def _format_generated_at(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    # Compact ISO-8601 with offset; exporter accepts this form.
    return dt.isoformat().replace("+00:00", "+00:00")


# ═══════════════════════════════════════════════════════════════════════
#  Subprocess
# ═══════════════════════════════════════════════════════════════════════


def _run_subprocess(
    argv: list[str],
    *,
    config: MirrorConfig,
    cwd: Path,
    provider: str = "repo2md",
) -> str:
    """Run *argv* with shell=False; return stdout text or raise."""
    timeout = float(config.timeout_seconds)
    env = os.environ.copy()
    # Prefer explicit generated-at on argv; still allow SOURCE_DATE_EPOCH.
    try:
        completed = subprocess.run(
            argv,
            capture_output=True,
            text=True,
            cwd=str(cwd),
            timeout=timeout,
            shell=False,
            check=False,
            env=env,
        )
    except FileNotFoundError as exc:
        raise MirrorProviderError(
            f"{provider} executable not found: {argv[0]!r}",
            provider=provider,
            code="executable_not_found",
            details={"command_basename": Path(argv[0]).name},
        ) from exc
    except subprocess.TimeoutExpired as exc:
        raise MirrorProviderError(
            f"{provider} timed out after {timeout}s",
            provider=provider,
            code="timeout",
            details={"timeout_seconds": timeout},
        ) from exc
    except OSError as exc:
        raise MirrorProviderError(
            f"{provider} subprocess OS error: {exc}",
            provider=provider,
            code="os_error",
            details={"exception_type": type(exc).__name__},
        ) from exc

    if completed.returncode != 0:
        # Truncate stderr for non-secret diagnostics (no full dump of env).
        stderr = (completed.stderr or "").strip()
        if len(stderr) > 800:
            stderr = stderr[:800] + "…"
        raise MirrorProviderError(
            f"{provider} exited with code {completed.returncode}"
            + (f": {stderr}" if stderr else ""),
            provider=provider,
            code="nonzero_exit",
            details={"returncode": completed.returncode},
        )

    return completed.stdout or ""


# ═══════════════════════════════════════════════════════════════════════
#  JSON + validation
# ═══════════════════════════════════════════════════════════════════════


def _parse_export_json(
    raw: str, *, config: MirrorConfig, provider: str = "repo2md"
) -> dict[str, Any]:
    text = (raw or "").strip()
    if not text:
        raise MirrorProviderError(
            f"{provider} produced empty stdout (expected versioned export JSON)",
            provider=provider,
            code="empty_stdout",
        )
    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise MirrorProviderError(
            f"{provider} stdout is not valid JSON: {exc}",
            provider=provider,
            code="malformed_json",
        ) from exc
    if not isinstance(data, dict):
        raise MirrorProviderError(
            f"{provider} export JSON must be an object",
            provider=provider,
            code="malformed_json",
        )

    schema_ver = data.get("export_schema_version")
    if schema_ver != config.expected_export_schema_version:
        raise MirrorProviderError(
            f"export_schema_version mismatch: got {schema_ver!r}, "
            f"expected {config.expected_export_schema_version!r}",
            provider=provider,
            code="schema_mismatch",
            details={
                "got": schema_ver,
                "expected": config.expected_export_schema_version,
            },
        )

    # Export-level errors from the tool are hard failures (partial not accepted).
    errors = data.get("errors") or []
    if errors:
        first = (
            errors[0] if isinstance(errors[0], dict) else {"message": str(errors[0])}
        )
        msg = first.get("message") or first.get("stage") or "export reported errors"
        raise MirrorProviderError(
            f"{provider} export reported errors: {msg}",
            provider=provider,
            code="export_errors",
            details={"error_count": len(errors)},
        )

    if "written" not in data or not isinstance(data.get("written"), list):
        raise MirrorProviderError(
            f"{provider} export JSON missing 'written' list",
            provider=provider,
            code="malformed_json",
        )
    return data


def validate_repo2md_export(
    export: dict[str, Any],
    *,
    repo_root: Path,
    output_root: Path,
    config: MirrorConfig,
    knowledge_dir: str = _DEFAULT_KNOWLEDGE_DIR,
    provider: str = "repo2md",
) -> list[dict[str, Any]]:
    """Validate written mirrors on disk against frozen AKMS v2 schema.

    Mirrors must lie under ``<output_root>/<knowledge_dir>/code-mirror``.
    Rejects path escape, missing files (partial output), frontmatter
    schema mismatch, content_ref/source_file inconsistency, and
    duplicate node IDs.
    """
    knowledge_prefix = f"{knowledge_dir}/"
    written = export.get("written") or []
    mirrors: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    seen_paths: set[str] = set()

    for entry in written:
        if not isinstance(entry, dict):
            raise MirrorProviderError(
                "written entry must be an object",
                provider=provider,
                code="malformed_json",
            )
        generated_path = entry.get("generated_path")
        content_ref = entry.get("content_ref")
        source_path = entry.get("source_path")
        node_id = entry.get("node_id")

        if not generated_path or not isinstance(generated_path, str):
            raise MirrorProviderError(
                "written entry missing generated_path",
                provider=provider,
                code="incomplete_output",
            )
        if not content_ref or not isinstance(content_ref, str):
            raise MirrorProviderError(
                f"written entry missing content_ref for {generated_path!r}",
                provider=provider,
                code="incomplete_output",
            )
        if not source_path or not isinstance(source_path, str):
            raise MirrorProviderError(
                f"written entry missing source_path for {generated_path!r}",
                provider=provider,
                code="incomplete_output",
            )
        if not node_id or not isinstance(node_id, str):
            raise MirrorProviderError(
                f"written entry missing node_id for {generated_path!r}",
                provider=provider,
                code="incomplete_output",
            )

        # Containment: generated_path must be under <knowledge dir>/code-mirror
        # and must not escape via .. components.
        _assert_mirror_path_safe(
            generated_path, knowledge_dir=knowledge_dir, provider=provider
        )
        _assert_mirror_path_safe(
            content_ref
            if content_ref.startswith(knowledge_prefix)
            else f"{knowledge_prefix}{content_ref}",
            knowledge_dir=knowledge_dir,
            provider=provider,
        )

        # content_ref is typically "code-mirror/..." while generated_path is
        # "<knowledge dir>/code-mirror/...".
        expected_ref_from_gen = generated_path
        if expected_ref_from_gen.startswith(knowledge_prefix):
            expected_ref_suffix = expected_ref_from_gen[len(knowledge_prefix) :]
        else:
            expected_ref_suffix = expected_ref_from_gen
        if content_ref not in (expected_ref_suffix, expected_ref_from_gen):
            # Allow content_ref without the knowledge-dir prefix (export contract).
            if content_ref.lstrip("/") != expected_ref_suffix.lstrip("/"):
                raise MirrorProviderError(
                    f"content_ref/generated_path mismatch: {content_ref!r} vs {generated_path!r}",
                    provider=provider,
                    code="content_ref_mismatch",
                )

        abs_path = (output_root / generated_path).resolve()
        try:
            abs_path.relative_to(output_root.resolve())
        except ValueError as exc:
            raise MirrorProviderError(
                f"path escape: generated file outside output root: {generated_path!r}",
                provider=provider,
                code="path_escape",
            ) from exc

        if not abs_path.is_file():
            raise MirrorProviderError(
                f"partial output: written file missing on disk: {generated_path!r}",
                provider=provider,
                code="partial_output",
            )

        # Frontmatter validation against frozen CodeMirrorNodeFrontmatter.
        try:
            post = fm.loads(abs_path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise MirrorProviderError(
                f"failed to read mirror file {generated_path!r}: {exc}",
                provider=provider,
                code="unreadable_mirror",
            ) from exc

        meta = dict(post.metadata or {})
        try:
            parsed = parse_node_frontmatter_from_dict(
                meta,
                is_code_mirror=True,
                path=str(abs_path),
            )
        except (SchemaValidationError, SchemaVersionError) as exc:
            raise MirrorProviderError(
                f"mirror frontmatter invalid for {generated_path!r}: {exc}",
                provider=provider,
                code="frontmatter_invalid",
            ) from exc

        # Schema version pin.
        akms_schema = getattr(parsed, "akms_schema", meta.get("akms_schema"))
        if akms_schema != config.expected_akms_schema_version:
            raise MirrorProviderError(
                f"akms_schema mismatch in {generated_path!r}: "
                f"got {akms_schema!r}, expected {config.expected_akms_schema_version!r}",
                provider=provider,
                code="schema_mismatch",
            )

        fm_source = getattr(parsed, "source_file", meta.get("source_file"))
        fm_content_ref = getattr(parsed, "content_ref", meta.get("content_ref"))
        fm_id = getattr(parsed, "id", meta.get("id"))

        if fm_source != source_path:
            raise MirrorProviderError(
                f"source_file mismatch in {generated_path!r}: "
                f"frontmatter={fm_source!r} export={source_path!r}",
                provider=provider,
                code="source_file_mismatch",
            )
        if fm_content_ref not in (content_ref, expected_ref_suffix, generated_path):
            # Normalize both sides without the knowledge-dir prefix.
            a = str(fm_content_ref).removeprefix(knowledge_prefix)
            b = str(content_ref).removeprefix(knowledge_prefix)
            if a != b:
                raise MirrorProviderError(
                    f"content_ref mismatch in {generated_path!r}: "
                    f"frontmatter={fm_content_ref!r} export={content_ref!r}",
                    provider=provider,
                    code="content_ref_mismatch",
                )
        if fm_id != node_id:
            raise MirrorProviderError(
                f"node_id mismatch in {generated_path!r}: "
                f"frontmatter={fm_id!r} export={node_id!r}",
                provider=provider,
                code="node_id_mismatch",
            )

        if node_id in seen_ids:
            raise MirrorProviderError(
                f"duplicate node_id in export: {node_id!r}",
                provider=provider,
                code="duplicate_id",
            )
        seen_ids.add(node_id)

        if generated_path in seen_paths:
            raise MirrorProviderError(
                f"duplicate generated_path in export: {generated_path!r}",
                provider=provider,
                code="duplicate_path",
            )
        seen_paths.add(generated_path)

        mirrors.append(
            {
                "source_file": source_path,
                "mirror_path": str(abs_path),
                "node_id": node_id,
                "definitions_count": 0,  # unknown to exporter summary
                "language": entry.get("language"),
                "content_ref": content_ref,
                "generated_path": generated_path,
            }
        )

    return mirrors


def _assert_mirror_path_safe(
    path_str: str,
    *,
    knowledge_dir: str = _DEFAULT_KNOWLEDGE_DIR,
    provider: str = "repo2md",
) -> None:
    """Reject absolute, drive-qualified, UNC, and `..` escape paths."""
    if not path_str or not isinstance(path_str, str):
        raise MirrorProviderError(
            f"Invalid mirror path: {path_str!r}",
            provider=provider,
            code="path_escape",
        )
    # Drive-qualified / UNC / absolute.
    if path_str.startswith(("/", "\\")) or (len(path_str) > 1 and path_str[1] == ":"):
        raise MirrorProviderError(
            f"path escape: absolute or drive-qualified path rejected: {path_str!r}",
            provider=provider,
            code="path_escape",
        )
    if path_str.startswith("\\\\") or path_str.startswith("//"):
        raise MirrorProviderError(
            f"path escape: UNC path rejected: {path_str!r}",
            provider=provider,
            code="path_escape",
        )
    pure = PurePosixPath(path_str.replace("\\", "/"))
    if ".." in pure.parts:
        raise MirrorProviderError(
            f"path escape: '..' component rejected: {path_str!r}",
            provider=provider,
            code="path_escape",
        )
    # Must live under <knowledge dir>/code-mirror (or code-mirror/ for content_ref).
    mirror_prefix = f"{knowledge_dir}/code-mirror"
    posix = pure.as_posix()
    if not (
        posix == mirror_prefix
        or posix.startswith(mirror_prefix + "/")
        or posix == "code-mirror"
        or posix.startswith("code-mirror/")
    ):
        raise MirrorProviderError(
            f"path escape: mirror path outside {mirror_prefix}: {path_str!r}",
            provider=provider,
            code="path_escape",
        )


def _parse_skipped_paths(export: dict[str, Any]) -> list[str]:
    """Source paths the exporter skipped because they did not parse, sorted."""
    paths: set[str] = set()
    for entry in export.get("skipped") or []:
        if not isinstance(entry, dict) or entry.get("reason") != "parse_error":
            continue
        sp = entry.get("source_path")
        if isinstance(sp, str):
            paths.add(sp)
    return sorted(paths)


def _python_sources_from_export(
    export: dict[str, Any],
    explicit: list[str] | None,
    parse_skipped: list[str] | None = None,
) -> list[str]:
    if explicit is not None:
        skipped = set(parse_skipped or [])
        return [p for p in explicit if p.endswith(".py") and p not in skipped]
    out: list[str] = []
    for entry in export.get("written") or []:
        if not isinstance(entry, dict):
            continue
        sp = entry.get("source_path")
        if isinstance(sp, str) and sp.endswith(".py"):
            out.append(sp)
    return out


def _run_python_drift(
    *,
    repo_root: Path,
    source_files: list[str],
    llm_fn: Any,
) -> list[dict[str, Any]]:
    """Provider-neutral structural (or optional LLM) drift on Python sources."""
    from akms.graph.drift import (
        check_docstring_drift_llm,
        check_docstring_drift_structural,
        extract_definitions_from_source,
    )

    warnings: list[dict[str, Any]] = []
    for source_file in source_files:
        path = repo_root / source_file
        if not path.is_file():
            continue
        try:
            source = path.read_text(encoding="utf-8")
        except OSError:
            continue
        definitions = extract_definitions_from_source(source)
        if llm_fn is not None:
            file_warnings = check_docstring_drift_llm(definitions, llm_fn)
        else:
            file_warnings = check_docstring_drift_structural(definitions)
        for w in file_warnings:
            w["file"] = source_file
        warnings.extend(file_warnings)
    return warnings


class BuiltinMirrorProvider(Repo2mdMirrorProvider):
    """The exporter shipped in akms, run as ``python -m akms.repo_wiki``.

    It needs no separate install and writes mirrors into the knowledge
    directory ``build_graph`` reads (``.knowledge/`` or a legacy
    ``knowledge/``). ``MirrorConfig.command`` is ignored.
    """

    name = "builtin"
    cli = "python -m akms.repo_wiki export-akms"

    def command(self, config: MirrorConfig) -> list[str]:
        return [sys.executable, "-m", "akms.repo_wiki"]

    def strict_parse(self, config: MirrorConfig) -> bool:
        return config.strict_parse

    def knowledge_dir(self, output_root: Path) -> str | None:
        return local_knowledge_dir(output_root).name

    def generate(self, request: MirrorRequest, config: MirrorConfig) -> MirrorResult:
        # Changed-file selection needs the git base ref. Without one, match the
        # legacy provider (the previous default): warn and select nothing,
        # rather than failing every refresh in a repository without that ref.
        # A caller that requires success gets a failure instead.
        mode = (request.selection_mode or "changed").strip().lower()
        if request.source_files is None and mode in ("changed", "git"):
            base = request.git_base or request.parent_branch or "main"
            reason = _missing_git_ref(Path(request.repo_root), base)
            if reason is not None and config.require_success:
                raise MirrorProviderError(
                    f"changed-file selection is unavailable: {reason}",
                    provider=self.name,
                    code="selection_unavailable",
                )
            if reason is not None:
                logger.warning("builtin mirror provider selected no files: %s", reason)
                return MirrorResult(
                    provider=self.name,
                    provider_metadata={
                        "kind": "subprocess",
                        "cli": self.cli,
                        "selection": "skipped",
                        "reason": reason,
                    },
                )
        return super().generate(request, config)


def _missing_git_ref(repo_root: Path, ref: str) -> str | None:
    """Why ``ref`` cannot serve as a git diff base in ``repo_root``, or None."""
    try:
        completed = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", "--quiet"]
            + [f"{ref}^{{commit}}"],
            capture_output=True,
            text=True,
            timeout=30,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return f"git is unavailable: {exc}"
    if completed.returncode != 0:
        return f"git ref {ref!r} is not available in {repo_root.name!r}"
    return None

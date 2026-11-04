"""Pinned toolchain preflight and single-writer deterministic refresh."""

from __future__ import annotations

import base64
import email.parser
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any

from akms.layout import local_knowledge_dir
from akms.graph.build_graph import build_graph
from akms.graph.mirror_provider import MirrorRequest, run_mirror_provider
from akms.repo_wiki.export.akms import EXPORT_SCHEMA_VERSION
from akms.schema.models import MirrorConfig

import akms
from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.config import (
    ProjectConfig,
    load_project_config,
    version_pin_matches,
)
from akms_failure_memory.errors import FailureMemoryError
from akms_failure_memory.lesson_index import lesson_index_paths
from akms_failure_memory.locks import ProjectLock

_PUBLIC_SOURCE_PATHS = (
    "Packages/AKMS/src/akms/__init__.py",
    "Packages/AKMS/src/akms/cli/commands.py",
    "Packages/AKMS/src/akms/cli/provider_commands.py",
    "Packages/AKMS/src/akms/graph/build_graph.py",
    "Packages/AKMS/src/akms/graph/generate_loadout.py",
    "Packages/AKMS/src/akms/graph/generate_mirror.py",
    "Packages/AKMS/src/akms/graph/mirror_provider.py",
    "Packages/AKMS/src/akms/graph/query_subgraph.py",
    "Packages/AKMS/src/akms/orchestrator/mcp_tools.py",
    "Packages/AKMS/src/akms/schema/models.py",
    "Packages/AKMS/src/akms/task_context/manifest.py",
    "Packages/AKMS/src/akms/task_context/models.py",
    "Packages/AKMS/src/akms/task_context/query.py",
    "Packages/AKMS/src/akms/task_context/resolve.py",
    "Packages/AKMS/src/akms/task_context/resolve_task_service.py",
    "Packages/AKMS/src/akms/task_context/review.py",
    "Packages/AKMS/src/akms/task_context/routes.py",
)


def _akms_public_digest() -> str:
    package_src = Path(akms.__file__).resolve().parents[1]
    digest = hashlib.sha256()
    prefix = PurePosixPath("Packages/AKMS/src")
    for relative in _PUBLIC_SOURCE_PATHS:
        path = package_src.joinpath(*PurePosixPath(relative).relative_to(prefix).parts)
        try:
            content = path.read_bytes()
        except OSError as exc:
            raise FailureMemoryError(
                f"Cannot read pinned AKMS source {path}: {exc}", code="akms_contract"
            ) from exc
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    return digest.hexdigest()


def _resolve_command(command: tuple[str, ...]) -> tuple[str, ...]:
    executable = command[0]
    if "/" in executable or "\\" in executable:
        resolved = Path(executable).expanduser().resolve(strict=False)
        if not resolved.is_file() or not os.access(resolved, os.X_OK):
            raise FailureMemoryError(
                f"repo2md executable is unavailable: {resolved}", code="repo2md_missing"
            )
        return (str(resolved), *command[1:])
    resolved = shutil.which(executable)
    if resolved is None:
        raise FailureMemoryError(
            f"repo2md executable is unavailable: {executable}", code="repo2md_missing"
        )
    return (str(Path(resolved).resolve()), *command[1:])


def _run(
    argv: list[str], *, cwd: Path, timeout: float
) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            argv,
            cwd=cwd,
            capture_output=True,
            text=True,
            timeout=timeout,
            shell=False,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise FailureMemoryError(
            f"Toolchain command failed: {exc}", code="toolchain_command"
        ) from exc


def _installed_distribution(executable: str) -> tuple[str, Path] | None:
    """Return adjacent distribution metadata and its editable source checkout."""
    resolved = Path(executable).resolve()
    candidates = sorted(
        resolved.parents[1].glob("lib/python*/site-packages/repo2md-*.dist-info")
    )
    for metadata_path in candidates:
        try:
            message = email.parser.Parser().parsestr(
                (metadata_path / "METADATA").read_text(encoding="utf-8")
            )
            entry_points = (metadata_path / "entry_points.txt").read_text(
                encoding="utf-8"
            )
            if "repo-wiki = repo2md.cli:main" not in entry_points.splitlines():
                continue
            executable_hash = (
                base64.urlsafe_b64encode(hashlib.sha256(resolved.read_bytes()).digest())
                .decode("ascii")
                .rstrip("=")
            )
            registered = False
            for line in (
                (metadata_path / "RECORD").read_text(encoding="utf-8").splitlines()
            ):
                fields = line.split(",")
                if len(fields) >= 2 and fields[1] == f"sha256={executable_hash}":
                    if (metadata_path.parent / fields[0]).resolve(
                        strict=False
                    ) == resolved:
                        registered = True
                        break
            if not registered:
                continue
            direct = json.loads(
                (metadata_path / "direct_url.json").read_text(encoding="utf-8")
            )
            url = urllib.parse.urlparse(str(direct["url"]))
            if url.scheme != "file" or not direct.get("dir_info", {}).get("editable"):
                continue
            checkout = Path(urllib.parse.unquote(url.path)).resolve(strict=True)
        except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        version = message.get("Version")
        if version:
            return version, checkout
    return None


def _checkout_version(tool_root: Path) -> str:
    try:
        return str(
            tomllib.loads((tool_root / "pyproject.toml").read_text(encoding="utf-8"))[
                "project"
            ]["version"]
        )
    except (OSError, KeyError, tomllib.TOMLDecodeError) as exc:
        raise FailureMemoryError(
            "Cannot verify repo2md checkout package version", code="repo2md_version"
        ) from exc


def _fixture_identity(tool_root: Path) -> tuple[str, int, str]:
    pin_path = tool_root / "dev/plans/akms_mirror_export/release/integration_pin.json"
    try:
        pin = json.loads(pin_path.read_text(encoding="utf-8"))
        fixture_root = tool_root.joinpath(
            *PurePosixPath(str(pin["fixture_root"])).parts
        )
        files = pin["files"]
    except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
        raise FailureMemoryError(
            "Cannot read repo2md integration pin", code="repo2md_fixture"
        ) from exc
    if (
        pin.get("package") != "repo2md"
        or pin.get("fixture_contract_version") != 1
        or not isinstance(pin.get("export_schema_version"), int)
        or pin.get("akms_schema_version") != akms.AKMS_SCHEMA_VERSION
        or not isinstance(pin.get("version"), str)
        or not isinstance(files, list)
    ):
        raise FailureMemoryError(
            "repo2md integration pin has an incompatible schema", code="repo2md_fixture"
        )
    digest = hashlib.sha256()
    for entry in files:
        try:
            relative = PurePosixPath(str(entry["path"]))
            if relative.is_absolute() or any(
                part in {"", ".", ".."} for part in relative.parts
            ):
                raise ValueError
            path = fixture_root.joinpath(*relative.parts)
            if path.is_symlink() or not path.resolve(strict=True).is_relative_to(
                fixture_root.resolve(strict=True)
            ):
                raise ValueError
            content = path.read_bytes()
            if (
                len(content) != entry["size"]
                or hashlib.sha256(content).hexdigest() != entry["sha256"]
            ):
                raise ValueError
        except (OSError, KeyError, TypeError, ValueError) as exc:
            raise FailureMemoryError(
                "repo2md fixture contents do not match the integration pin",
                code="repo2md_fixture",
            ) from exc
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(content)
        digest.update(b"\0")
    observed = digest.hexdigest()
    if observed != pin.get("fixture_pack_sha256"):
        raise FailureMemoryError(
            "repo2md fixture pack digest is invalid", code="repo2md_fixture"
        )
    return str(pin["version"]), int(pin["export_schema_version"]), observed


def preflight(*, config: ProjectConfig, repository_root: str | Path) -> dict[str, Any]:
    """Check that the installed AKMS is usable and repo2md is callable.

    This is deliberately NOT an identity check. It blocks on exactly two things:

      * the installed AKMS schema version is incompatible with the project, and
      * repo2md cannot be invoked with the export contract this package needs.

    Both are conditions under which the next step genuinely cannot run.

    Everything else — the AKMS version string, the AKMS public-API digest, and
    the repo2md checkout version / commit / cleanliness / fixture digest — is
    reported as an advisory and never raises. Those answer "is this the exact
    artifact we certified?", which matters when publishing a release, not when a
    developer is using the tool. Enforcing them on every resolve made ordinary,
    correct edits to AKMS fail closed here, so pins got chased instead of code
    getting fixed: the duplicated run_qmd.sh lookup in
    ``akms.graph.generate_loadout`` survived precisely because removing it would
    have tripped the public-API digest.

    Advisories are returned under ``advisories`` so drift stays visible.
    Publication paths that do need exact identity should compare these values
    themselves rather than relying on this function to refuse.
    """
    root = Path(repository_root).resolve(strict=True)
    advisories: list[dict[str, Any]] = []

    def note(code: str, message: str, **details: Any) -> None:
        entry: dict[str, Any] = {"code": code, "message": message}
        if details:
            entry["details"] = details
        advisories.append(entry)

    # ── Blocking: schema compatibility ────────────────────────────────────
    # A v2 project cannot be served by an AKMS that speaks a different schema.
    if akms.AKMS_SCHEMA_VERSION != config.toolchain["akms_schema_version"]:
        raise FailureMemoryError(
            "Installed AKMS schema is incompatible", code="akms_contract"
        )

    # ── Advisory: AKMS identity ───────────────────────────────────────────
    # The pin is a plain version (exact match) or a PEP 440 range.
    pinned_version = config.toolchain.get("akms_version")
    if pinned_version and not version_pin_matches(pinned_version, akms.__version__):
        note(
            "akms_version_drift",
            "Installed AKMS version differs from the project pin",
            actual=akms.__version__,
            expected=pinned_version,
        )

    try:
        digest = _akms_public_digest()
    except FailureMemoryError as exc:
        digest = ""
        note("akms_public_api_unreadable", str(exc))
    pinned_digest = config.toolchain.get("akms_public_api_sha256")
    if pinned_digest and digest and digest != pinned_digest:
        note(
            "akms_public_api_drift",
            "Installed AKMS public API differs from the project pin",
            actual=digest,
            expected=pinned_digest,
        )

    # ── Blocking: the mirror exporter must actually be callable ───────────
    if config.mirror_provider == "builtin":
        command = _BUILTIN_COMMAND
        _require_export_contract(
            command, root, config, flags=_BUILTIN_CONTRACT_FLAGS, provider="builtin"
        )
        mirror: dict[str, Any] = {
            "provider": "builtin",
            "command": list(command),
            "version": akms.__version__,
            "export_schema_version": EXPORT_SCHEMA_VERSION,
        }
        repo2md = None
    else:
        repo2md = _repo2md_identity(config, root, note)
        mirror = {
            "provider": "repo2md",
            "command": repo2md["command"],
            "version": repo2md["version"],
            "export_schema_version": repo2md["export_schema_version"],
        }

    identity: dict[str, Any] = {
        "status": "ok",
        "advisories": advisories,
        "akms": {
            "version": akms.__version__,
            "schema": akms.AKMS_SCHEMA_VERSION,
            "public_api_sha256": digest,
        },
        "mirror": mirror,
    }
    if repo2md is not None:
        identity["repo2md"] = repo2md
    return identity


# The exporter shipped in akms, run with the interpreter that runs this package.
_BUILTIN_COMMAND = (sys.executable, "-m", "akms.repo_wiki")
_CONTRACT_FLAGS = ("--output", "--phase", "--json")
_BUILTIN_CONTRACT_FLAGS = (*_CONTRACT_FLAGS, "--knowledge-dir")


def _require_export_contract(
    command: tuple[str, ...],
    root: Path,
    config: ProjectConfig,
    *,
    flags: tuple[str, ...],
    provider: str,
) -> None:
    contract = _run(
        [*command, "export-akms", "--help"],
        cwd=root,
        timeout=float(config.toolchain["timeout_seconds"]),
    )
    contract_text = contract.stdout + contract.stderr
    if contract.returncode != 0 or any(flag not in contract_text for flag in flags):
        raise FailureMemoryError(
            f"{provider} export-akms CLI contract is unavailable",
            code="repo2md_contract",
        )


def _repo2md_identity(config: ProjectConfig, root: Path, note: Any) -> dict[str, Any]:
    """Check the external repo-wiki is callable; report its identity as advisories."""
    command = _resolve_command(tuple(config.toolchain["repo2md_command"]))
    _require_export_contract(
        command, root, config, flags=_CONTRACT_FLAGS, provider="repo2md"
    )

    # ── Advisory: repo2md identity, best effort ───────────────────────────
    distribution = _installed_distribution(command[0])
    metadata_version, editable_root = distribution if distribution else ("", None)
    if distribution is None:
        note(
            "repo2md_distribution_unknown",
            "repo2md is not linked to a verifiable editable distribution",
        )

    configured_root = config.toolchain.get("repo2md_root")
    environment_root = os.environ.get("AKMS_REPO2MD_ROOT")
    tool_root: Path | None
    try:
        if configured_root:
            tool_root = root.joinpath(
                *PurePosixPath(str(configured_root)).parts
            ).resolve(strict=True)
        elif environment_root:
            tool_root = Path(environment_root).expanduser().resolve(strict=True)
        else:
            tool_root = editable_root
    except OSError as exc:
        tool_root = editable_root
        note(
            "repo2md_root_unresolved", f"Cannot resolve configured repo2md root: {exc}"
        )

    if (
        tool_root is not None
        and editable_root is not None
        and tool_root != editable_root
    ):
        note(
            "repo2md_checkout_mismatch",
            "repo2md executable is not linked to the configured checkout",
            configured=str(tool_root),
            linked=str(editable_root),
        )

    checkout_version = ""
    observed_commit = ""
    observed_dirty = False
    export_schema = config.toolchain.get("repo2md_export_schema_version")
    fixture_sha = ""

    if tool_root is not None:
        try:
            checkout_version = _checkout_version(tool_root)
        except Exception as exc:  # noqa: BLE001 - advisory only
            note("repo2md_version_unknown", f"Cannot read repo2md version: {exc}")
        expected_version = str(config.toolchain["repo2md_version"])
        if checkout_version and not version_pin_matches(
            expected_version, checkout_version
        ):
            note(
                "repo2md_version_drift",
                "repo2md version differs from the project pin",
                actual=checkout_version,
                expected=expected_version,
            )

        head = _run(
            ["git", "-C", str(tool_root), "rev-parse", "HEAD"],
            cwd=root,
            timeout=float(config.toolchain["timeout_seconds"]),
        )
        observed_commit = head.stdout.strip()
        if head.returncode != 0:
            note("repo2md_commit_unknown", "Cannot read repo2md checkout commit")
        elif observed_commit != config.toolchain["repo2md_commit"]:
            note(
                "repo2md_commit_drift",
                "repo2md checkout is not at the pinned commit",
                actual=observed_commit,
                expected=config.toolchain["repo2md_commit"],
            )

        dirty = _run(
            ["git", "-C", str(tool_root), "status", "--porcelain"],
            cwd=root,
            timeout=float(config.toolchain["timeout_seconds"]),
        )
        if dirty.returncode != 0:
            note("repo2md_dirty_unknown", "Cannot inspect repo2md checkout state")
        else:
            observed_dirty = bool(dirty.stdout)
            if (
                config.toolchain["repo2md_dirty_policy"] == "require-clean"
                and observed_dirty
            ):
                note("repo2md_dirty", "repo2md checkout has uncommitted changes")

        try:
            pin_version, observed_schema, fixture_sha = _fixture_identity(tool_root)
            export_schema = observed_schema
            if checkout_version and pin_version != checkout_version:
                note(
                    "repo2md_pin_version_drift",
                    "repo2md integration pin version does not match the checkout",
                    actual=pin_version,
                    expected=checkout_version,
                )
            if observed_schema != config.toolchain["repo2md_export_schema_version"]:
                note(
                    "repo2md_export_schema_drift",
                    "repo2md export schema differs from the project pin",
                    actual=observed_schema,
                    expected=config.toolchain["repo2md_export_schema_version"],
                )
            pinned_fixture = config.toolchain.get("repo2md_fixture_sha256")
            if pinned_fixture and fixture_sha != pinned_fixture:
                note(
                    "repo2md_fixture_drift",
                    "repo2md fixture digest differs from the project pin",
                    actual=fixture_sha,
                    expected=pinned_fixture,
                )
        except FailureMemoryError as exc:
            note("repo2md_fixture_unreadable", str(exc))

    if metadata_version and checkout_version and metadata_version != checkout_version:
        # Editable installers may retain stale wheel metadata; the checkout is
        # the observed authority.
        metadata_status = "stale"
    else:
        metadata_status = "current"

    return {
        "command": list(command),
        "checkout": str(tool_root) if tool_root is not None else "",
        "version": checkout_version,
        "distribution_version": metadata_version,
        "distribution_metadata": metadata_status,
        "export_schema_version": export_schema,
        "fixture_sha256": fixture_sha,
        "commit": observed_commit,
        "dirty": observed_dirty,
    }


def _timestamp(value: str | None) -> datetime:
    if not value:
        raise FailureMemoryError(
            "Mirror refresh requires explicit deterministic --generated-at metadata",
            code="generated_at_required",
        )
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise FailureMemoryError(
            "generated_at must be ISO-8601", code="generated_at_invalid"
        ) from exc
    if parsed.tzinfo is None:
        raise FailureMemoryError(
            "generated_at must include a timezone", code="generated_at_invalid"
        )
    return parsed


def _mirror(
    config: ProjectConfig,
    root: Path,
    *,
    phase: int,
    generated_at: str | None,
    identity: dict[str, Any],
    git_base: str | None = None,
) -> dict[str, Any]:
    """Run the configured exporter.

    Without ``git_base`` this is the configured selection with pruning, as
    ``refresh mirror`` has always run it. With ``git_base`` the exporter's own
    git selection picks the sources that differ between that commit and the
    worktree (deleted sources lose their mirrors); nothing else is pruned,
    because the exporter refuses to prune a partial selection.
    """
    provider = config.mirror_provider
    command = identity["mirror"]["command"]
    selection = str(config.toolchain["mirror_selection"]) if git_base is None else "git"
    prune = git_base is None
    mirror_config = MirrorConfig(
        provider=provider,
        command=command,
        timeout_seconds=float(config.toolchain["timeout_seconds"]),
        fallback_on_error=False,
        require_success=True,
        generated_at_source="request",
        selection_mode=selection,
        prune=prune,
        expected_export_schema_version=(
            EXPORT_SCHEMA_VERSION
            if provider == "builtin"
            else int(config.toolchain["repo2md_export_schema_version"])
        ),
        expected_akms_schema_version=str(config.toolchain["akms_schema_version"]),
    )
    request = MirrorRequest(
        repo_root=root,
        output_root=config.resolve(root, "akms_repo_root"),
        phase=phase,
        generated_at=_timestamp(generated_at),
        selection_mode=selection,
        drift_check=True,
        llm_fn=None,
        prune=prune,
        git_base=git_base,
    )
    result = run_mirror_provider(request, mirror_config, provider_name=provider)
    if not result.success:
        raise FailureMemoryError(
            f"{provider} mirror refresh failed", code="mirror_failure"
        )
    return {
        "status": "ok",
        "provider": result.provider,
        "files_processed": result.files_processed,
        "definitions_total": result.definitions_total,
        "provider_metadata": result.provider_metadata,
        "errors": result.errors,
    }


_EXTERNAL_GLOBAL_VAULT_MARKER = "<external-global-vault>"


def _canonical_global_vault(raw_value: Any) -> str:
    """Canonicalize ``graph.json`` graph.global_vault to a portable string.

    ``akms.graph.build_graph`` writes the fully-resolved, machine-specific
    absolute path of whatever vault directory it was pointed at (default
    ``~/.claude/akms/nodes``, or an ``AKMS_GLOBAL_VAULT``/test override).
    Two builds against the SAME logical vault content, mounted at two
    DIFFERENT absolute paths (a different machine, a different container, a
    different per-run temp directory in CI or tests), otherwise embed two
    different strings here -- and because ``graph_sha256`` hashes the whole
    published file, that alone changes ``graph_sha256`` and therefore
    ``result.fingerprint`` / ``result.resolution_fingerprint`` /
    ``resolution.graph_version``, even though nothing about the graph's
    actual content changed. The vault's CONTENT is already fully reflected
    in the compiled ``nodes``/``links`` arrays; the literal path it happens
    to be mounted at carries no additional identity information worth
    hashing.

    Frozen schema §8 (``docs/specification/AKMS_v2_specification.md``)
    illustrates this field with the tilde-collapsed form
    ``"~/.claude/akms/nodes"`` rather than a resolved absolute path, so
    collapsing a vault under the user's home directory back to that form is
    already the documented canonical shape -- this only makes build_graph's
    literal output match its own spec example. A vault that is NOT under
    home (every ephemeral/test/CI vault, and any explicit
    ``AKMS_GLOBAL_VAULT`` override outside ``$HOME``) collapses to a single
    fixed, non-host-specific marker instead, so any two such mounts compare
    equal regardless of their actual OS-assigned path. The field stays a
    plain string either way -- this changes its VALUE, not the frozen
    schema's shape, and touches no AKMS core file: build_graph still writes
    whatever absolute path it resolved, this project-owned finalizer (the
    same one that already overrides ``generated_at`` and ``repo_id`` below)
    rewrites it before publication, exactly like those two fields.
    """
    if not isinstance(raw_value, str) or not raw_value:
        return _EXTERNAL_GLOBAL_VAULT_MARKER
    home = str(Path.home())
    if raw_value == home:
        return "~"
    if raw_value.startswith(home + os.sep):
        return "~" + raw_value[len(home) :]
    return _EXTERNAL_GLOBAL_VAULT_MARKER


def _finalize_graph_payload(
    graph_data: Any,
    *,
    config: ProjectConfig,
    generated_at: datetime | str,
) -> bytes:
    """Apply canonical project-owned metadata to one raw AKMS graph payload."""
    metadata = graph_data["graph"]
    if not isinstance(metadata, dict):
        raise TypeError("graph metadata must be an object")
    metadata["generated_at"] = (
        generated_at.isoformat() if isinstance(generated_at, datetime) else generated_at
    )
    # The failure-memory project configuration owns repository identity.
    # AKMS local_state.yaml is experiential state, and its repo_id is only
    # informational; it must neither override this canonical identity nor be
    # synthesized or rewritten to communicate it to build_graph().
    metadata["repo_id"] = config.repository_id
    # Portable fingerprints (F3 requirement: a restarted session, a
    # different machine, or a different CI runner alone must not change the
    # deterministic result): the vault's mount path is a construction
    # input, not part of the graph's logical content, so it is canonicalized
    # the same way generated_at and repo_id already are above.
    metadata["global_vault"] = _canonical_global_vault(metadata.get("global_vault"))
    return json.dumps(graph_data, sort_keys=True, indent=2, default=str).encode("utf-8")


def _graph(
    config: ProjectConfig,
    root: Path,
    global_vault: Path,
    *,
    generated_at: str | None,
) -> dict[str, Any]:
    deterministic_timestamp = _timestamp(generated_at)
    output_path = config.resolve(root, "graph")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb",
            dir=output_path.parent,
            prefix=f".{output_path.name}.",
            suffix=".tmp",
            delete=False,
        ) as stream:
            temporary = Path(stream.name)
        graph = build_graph(
            config.resolve(root, "akms_repo_root"),
            global_vault=global_vault,
            output_path=temporary,
            strict=True,
        )
        try:
            graph_data = json.loads(temporary.read_text(encoding="utf-8"))
            content = _finalize_graph_payload(
                graph_data,
                config=config,
                generated_at=deterministic_timestamp,
            )
        except (OSError, KeyError, TypeError, json.JSONDecodeError) as exc:
            raise FailureMemoryError(
                "Cannot finalize deterministic AKMS graph metadata",
                code="graph_artifact",
            ) from exc
        with temporary.open("wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, output_path)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    return {
        "status": "ok",
        "nodes": graph.number_of_nodes(),
        "edges": graph.number_of_edges(),
        "graph": config.paths["graph"],
    }


def status(config: ProjectConfig, root: Path) -> dict[str, Any]:
    artifacts = {}
    for key in ("registry", "generated_nodes", "routes", "graph", "provider_outputs"):
        path = config.resolve(root, key)
        artifacts[key] = {
            "path": config.paths[key],
            "exists": path.exists(),
            "sha256": hashlib.sha256(path.read_bytes()).hexdigest()
            if path.is_file()
            else None,
        }
    return {
        "status": "ok",
        "artifacts": artifacts,
        "config_fingerprint": config.fingerprint,
    }


def _clean(config: ProjectConfig, root: Path) -> dict[str, Any]:
    candidates = []
    if config.generated["lessons"] == "disposable":
        candidates.append(config.resolve(root, "generated_nodes"))
        if config.lesson_index_version is not None:
            candidates.extend(
                root.joinpath(*PurePosixPath(relative).parts)
                for relative in lesson_index_paths(config)
            )
    if config.generated["routes"] == "disposable":
        candidates.append(config.resolve(root, "routes"))
    if config.generated["graph"] == "disposable":
        candidates.append(config.resolve(root, "graph"))
    akms_root = config.resolve(root, "akms_repo_root")
    knowledge = local_knowledge_dir(akms_root)
    if config.generated["mirror"] == "disposable":
        candidates.append(knowledge / "code-mirror")
        # The external repo-wiki always writes knowledge/code-mirror.
        repo2md_mirror = akms_root / "knowledge" / "code-mirror"
        if repo2md_mirror != knowledge / "code-mirror":
            candidates.append(repo2md_mirror)
    if config.generated["loadouts"] == "disposable":
        candidates.extend(
            [
                knowledge / "loadouts",
                knowledge / "resolution-manifests",
                config.resolve(root, "provider_outputs"),
            ]
        )
    removed = []
    for path in candidates:
        if path.is_symlink():
            raise FailureMemoryError(
                f"Refusing to clean symlink {path}", code="path_escape"
            )
        if not path.exists():
            continue
        if path.is_dir():
            shutil.rmtree(path)
        else:
            path.unlink()
        removed.append(path.relative_to(root).as_posix())
    return {"status": "cleaned", "removed": sorted(removed)}


# ── refresh if-stale ──────────────────────────────────────────────────────
# Where `refresh if-stale` records the commit its mirrors last matched. It is
# per worktree (`git rev-parse --git-path` puts it in the worktree's own git
# directory), untracked by construction, and only `if-stale` reads or writes it.
_STATE_GIT_PATH = "akms-failure-memory/refresh-state.json"
_STATE_VERSION = 1
# The exporter reads these to decide which files are sources, so a change to
# either can add or drop sources anywhere in the tree.
_SELECTION_INPUTS = frozenset({".gitignore", ".repo_wiki/config.yaml"})


def _current_utc() -> str:
    """The real current time, UTC, to the second.

    ``akms status`` reports a mirror stale when its source was committed or
    modified after the mirror's ``generated_at``, so the stamp must be "now".
    """
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _git_bytes(root: Path, *arguments: str) -> bytes | None:
    try:
        completed = subprocess.run(
            ["git", "-C", str(root), "-c", "core.quotepath=false", *arguments],
            capture_output=True,
            check=False,
            shell=False,
            timeout=120,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout if completed.returncode == 0 else None


def _git_text(root: Path, *arguments: str) -> str | None:
    output = _git_bytes(root, *arguments)
    if output is None:
        return None
    return output.decode("utf-8", errors="replace").strip() or None


def _commit(root: Path, ref: str | None) -> str | None:
    """The commit ``ref`` names, or None (unset, the all-zero ref, or unknown)."""
    if not ref or set(ref) == {"0"}:
        return None
    return _git_text(root, "rev-parse", "--verify", "--quiet", f"{ref}^{{commit}}")


def _git_names(root: Path, command: str, *arguments: str) -> set[str] | None:
    """A NUL-separated git path listing as a set, or None when git fails."""
    output = _git_bytes(root, command, "-z", *arguments)
    if output is None:
        return None
    return {
        item.decode("utf-8", errors="replace") for item in output.split(b"\0") if item
    }


def _mirror_identity(config: ProjectConfig) -> dict[str, str]:
    """What, besides the sources, decides the mirror bytes."""
    return {
        "provider": config.mirror_provider,
        "akms_repo_root": str(config.paths["akms_repo_root"]),
        "akms_version": akms.__version__,
    }


def _state_path(root: Path) -> Path | None:
    output = _git_text(root, "rev-parse", "--git-path", _STATE_GIT_PATH)
    if output is None:
        return None
    path = Path(output)
    return path if path.is_absolute() else root / path


def _read_state(root: Path) -> dict[str, Any] | None:
    path = _state_path(root)
    if path is None or not path.is_file():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None
    if not isinstance(state, dict) or state.get("version") != _STATE_VERSION:
        return None
    return state


def _write_state(root: Path, state: dict[str, Any]) -> str | None:
    """Record the refreshed commit; returns a warning instead of failing."""
    path = _state_path(root)
    if path is None:  # not a git worktree: there is nothing to diff against later
        return None
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
        temporary.write_text(
            json.dumps(state, sort_keys=True, indent=2) + "\n", encoding="utf-8"
        )
        os.replace(temporary, path)
    except OSError as exc:
        return f"cannot record the refreshed commit: {exc}"
    return None


def _mirror_plan(
    config: ProjectConfig, root: Path, since: str | None
) -> dict[str, Any]:
    """Decide between no mirror work, a changed-source export and a full one.

    Candidate bases are ``since`` and the commit the last ``if-stale`` refresh
    recorded, each with its merge base with HEAD: a rebase or an amend gives
    the commits it rewrote a new commit time, and ``akms status`` compares
    commit times, so the files those commits touch are refreshed too. The
    fewest bases that cover every changed path are exported.
    """
    head = _commit(root, "HEAD")

    def full(reason: str) -> dict[str, Any]:
        return {"selection": "full", "reason": reason, "bases": [], "head": head}

    top = _git_text(root, "rev-parse", "--show-toplevel")
    if top is None:
        return full("not a git worktree, so changed sources are unknown")
    if Path(top).resolve() != root:
        return full("the project root is not the git top level")
    knowledge = local_knowledge_dir(config.resolve(root, "akms_repo_root"))
    if not (knowledge / "code-mirror").is_dir():
        return full("there are no code mirrors yet")
    state = _read_state(root)
    recorded: str | None = None
    if state is not None and state.get("head"):
        if state.get("mirror") != _mirror_identity(config):
            return full(
                "the mirror provider, AKMS version or akms_repo_root changed "
                "since the last refresh"
            )
        recorded = _commit(root, state.get("head"))
    candidates = [commit for commit in (_commit(root, since), recorded) if commit]
    if not candidates:
        if since is not None and set(since) != {"0"}:
            return full(f"{since!r} is not a commit")
        return full("no base commit: neither --since nor a recorded refresh")
    if head is not None:
        for commit in list(candidates):
            merge_base = _git_text(root, "merge-base", commit, head)
            if merge_base:
                candidates.append(merge_base)
    candidates = list(dict.fromkeys(candidates))
    # What the exporter's `--git-base` selection considers: paths that differ
    # between the base and the worktree, plus untracked files outside its own
    # output. The exporter still decides which of them are sources.
    untracked = _git_names(root, "ls-files", "--others", "--exclude-standard")
    if untracked is None:
        return full("git cannot list untracked files")
    try:
        output = knowledge.relative_to(root).as_posix() + "/"
        untracked = {name for name in untracked if not name.startswith(output)}
    except ValueError:
        pass
    names: dict[str, set[str]] = {}
    for commit in candidates:
        changed = _git_names(root, "diff", "--name-only", "--no-renames", commit)
        if changed is None:
            return full(f"git cannot diff the worktree against {commit[:12]}")
        names[commit] = changed
    every = set().union(untracked, *names.values())
    if every & _SELECTION_INPUTS:
        return full(".gitignore or .repo_wiki/config.yaml changed")
    if not every:
        return {
            "selection": "none",
            "reason": "no file changed",
            "bases": [],
            "head": head,
        }
    bases: list[str] = []
    covered: set[str] = set()
    for commit in sorted(candidates, key=lambda item: -len(names[item])):
        if names[commit] - covered:
            bases.append(commit)
            covered |= names[commit]
    # Only untracked files changed: any one base selects them.
    bases = bases or candidates[:1]
    return {
        "selection": "changed",
        "reason": f"{len(every)} path(s) changed",
        "bases": bases,
        "head": head,
    }


def _refresh_lessons_if_stale(
    config: ProjectConfig, config_path: str | Path, root: Path, vault: Path
) -> dict[str, Any]:
    if (
        config.generated["lessons"] == "committed"
        and config.generated["routes"] == "committed"
    ):
        return {"status": "skipped", "reason": "generated lessons are committed"}
    # The same comparison `failure-memory check` makes: every expected output
    # byte, including the registry digest each node and the route index embed.
    checked = run_compiler(
        config_path=config_path,
        repository_root=root,
        global_vault=vault,
        mode="check",
    )
    if checked["status"] == "clean":
        return {"status": "current", "source_sha256": checked["source_sha256"]}
    written = run_compiler(
        config_path=config_path,
        repository_root=root,
        global_vault=vault,
        mode="write",
    )
    return {
        "status": "recompiled",
        "source_sha256": written["source_sha256"],
        "counts": written["counts"],
        "written": written["written"],
        "removed": written["stale"],
    }


def _refresh_mirror_if_stale(
    config: ProjectConfig,
    root: Path,
    *,
    since: str | None,
    phase: int,
    generated_at: str,
) -> dict[str, Any]:
    if config.generated["mirror"] == "committed":
        return {"status": "skipped", "reason": "code mirrors are committed"}
    plan = _mirror_plan(config, root, since)
    stage: dict[str, Any] = {
        "selection": plan["selection"],
        "reason": plan["reason"],
        "bases": plan["bases"],
        "written": 0,
        "removed": 0,
    }
    if plan["selection"] == "none":
        stage["status"] = "current"
    else:
        identity = preflight(config=config, repository_root=root)
        runs = (
            [
                _mirror(
                    config,
                    root,
                    phase=phase,
                    generated_at=generated_at,
                    identity=identity,
                )
            ]
            if plan["selection"] == "full"
            else [
                _mirror(
                    config,
                    root,
                    phase=phase,
                    generated_at=generated_at,
                    identity=identity,
                    git_base=base,
                )
                for base in plan["bases"]
            ]
        )
        for run in runs:
            metadata = run.get("provider_metadata") or {}
            stage["written"] += int(metadata.get("written_count", 0) or 0)
            stage["removed"] += int(metadata.get("removed_count", 0) or 0)
        stage["status"] = "refreshed"
        stage["provider"] = runs[0]["provider"] if runs else config.mirror_provider
    stage["head"] = plan["head"]
    return stage


def refresh_if_stale(
    *,
    config_path: str | Path,
    repository_root: str | Path,
    global_vault: str | Path,
    since: str | None = None,
    phase: int = 1,
    force_lock: bool = False,
    lock_timeout_seconds: float | None = None,
) -> dict[str, Any]:
    """Refresh only what is stale: lessons, then mirrors, then the graph.

    * Lessons recompile only when ``check`` finds drift (a changed registry
      digest, a missing node, a changed compiler).
    * Mirrors are exported only for sources that changed since ``since`` or
      the last recorded ``if-stale`` refresh, through the exporter's own git
      selection. Without a usable base, or when the inputs that decide which
      files are sources changed, it is the full configured refresh, and the
      result says why.
    * The graph is rebuilt when either changed, or when it is missing.

    Outputs the project marks ``committed`` are never rewritten. Everything is
    stamped with the current UTC time and runs under the project lock;
    ``lock_timeout_seconds=0`` gives up at once if another writer holds it.
    """
    config = load_project_config(config_path)
    root = Path(repository_root).resolve(strict=True)
    vault = Path(global_vault).resolve(strict=True)
    generated_at = _current_utc()
    timeout = (
        float(config.toolchain["timeout_seconds"])
        if lock_timeout_seconds is None
        else float(lock_timeout_seconds)
    )
    with ProjectLock(
        config.resolve(root, "lock"), timeout_seconds=timeout, force_stale=force_lock
    ):
        previous = _read_state(root) or {}
        warnings: list[str] = []

        def record(
            *, graph_pending: bool, head: Any, mirror: dict[str, Any] | None
        ) -> None:
            warning = _write_state(
                root,
                {
                    "version": _STATE_VERSION,
                    "head": head,
                    "generated_at": generated_at,
                    "mirror": mirror,
                    "graph_pending": graph_pending,
                },
            )
            if warning and warning not in warnings:
                warnings.append(warning)

        stages: dict[str, Any] = {
            "lessons": _refresh_lessons_if_stale(config, config_path, root, vault)
        }
        if stages["lessons"]["status"] == "recompiled":
            # Until the graph is rebuilt it lags the lessons, even if the
            # mirror stage below fails; the next run must still rebuild it.
            record(
                graph_pending=True,
                head=previous.get("head"),
                mirror=previous.get("mirror"),
            )
        stages["mirror"] = _refresh_mirror_if_stale(
            config, root, since=since, phase=phase, generated_at=generated_at
        )
        mirror = stages["mirror"]
        if mirror["status"] == "skipped":
            head, identity = previous.get("head"), previous.get("mirror")
        else:
            head, identity = mirror.pop("head", None), _mirror_identity(config)

        changed = stages["lessons"]["status"] == "recompiled" or (
            mirror["status"] == "refreshed"
            and (
                mirror["selection"] == "full"
                or mirror["written"] + mirror["removed"] > 0
            )
        )
        if config.generated["graph"] == "committed":
            stages["graph"] = {"status": "skipped", "reason": "the graph is committed"}
        elif (
            changed
            or previous.get("graph_pending") is True
            or not config.resolve(root, "graph").is_file()
        ):
            # Recorded first, so a graph build that fails is retried next time
            # even though the lessons and mirrors it needs are already current.
            record(graph_pending=True, head=head, mirror=identity)
            stages["graph"] = {
                **_graph(config, root, vault, generated_at=generated_at),
                "status": "rebuilt",
            }
        else:
            stages["graph"] = {"status": "current"}
        record(graph_pending=False, head=head, mirror=identity)
        return {
            "status": "ok",
            "action": "if-stale",
            "generated_at": generated_at,
            "since": since,
            "stages": stages,
            "warnings": warnings,
            "config_fingerprint": config.fingerprint,
        }


def refresh_project(
    *,
    action: str,
    config_path: str | Path,
    repository_root: str | Path,
    global_vault: str | Path,
    phase: int = 1,
    generated_at: str | None = None,
    force_lock: bool = False,
    since: str | None = None,
) -> dict[str, Any]:
    """Run one refresh stage or the ordered lessons→mirror→graph chain."""
    if action == "if-stale":
        if generated_at is not None:
            raise FailureMemoryError(
                "refresh if-stale always stamps the current UTC time; "
                "drop --generated-at",
                code="usage",
            )
        return refresh_if_stale(
            config_path=config_path,
            repository_root=repository_root,
            global_vault=global_vault,
            since=since,
            phase=phase,
            force_lock=force_lock,
        )
    if since is not None:
        raise FailureMemoryError(
            "--since applies only to refresh if-stale", code="usage"
        )
    config = load_project_config(config_path)
    root = Path(repository_root).resolve(strict=True)
    vault = Path(global_vault).resolve(strict=True)
    if action == "preflight":
        return preflight(config=config, repository_root=root)
    if action == "status":
        return status(config, root)
    with ProjectLock(
        config.resolve(root, "lock"),
        timeout_seconds=float(config.toolchain["timeout_seconds"]),
        force_stale=force_lock,
    ):
        if action == "clean":
            return _clean(config, root)
        identity = preflight(config=config, repository_root=root)
        stages = {}
        if action in {"lessons", "all"}:
            stages["lessons"] = run_compiler(
                config_path=config_path,
                repository_root=root,
                global_vault=vault,
                mode="write",
            )
        if action in {"mirror", "all"}:
            stages["mirror"] = _mirror(
                config, root, phase=phase, generated_at=generated_at, identity=identity
            )
        if action in {"graph", "all"}:
            stages["graph"] = _graph(config, root, vault, generated_at=generated_at)
        if not stages:
            raise FailureMemoryError(f"Unknown refresh action {action!r}", code="usage")
        return {
            "status": "ok",
            "action": action,
            "stages": stages,
            "toolchain": identity,
            "config_fingerprint": config.fingerprint,
        }


__all__ = ["preflight", "refresh_if_stale", "refresh_project", "status"]

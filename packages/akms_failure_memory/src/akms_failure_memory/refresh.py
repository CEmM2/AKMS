"""Pinned toolchain preflight and single-writer deterministic refresh."""

from __future__ import annotations

import base64
import email.parser
import hashlib
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import urllib.parse
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

from akms.graph.build_graph import build_graph
from akms.graph.mirror_provider import MirrorRequest, run_mirror_provider
from akms.schema.models import MirrorConfig

import akms
from akms_failure_memory.compiler import run_compiler
from akms_failure_memory.config import ProjectConfig, load_project_config
from akms_failure_memory.errors import FailureMemoryError
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
    pin_path = tool_root / "dev/plans/mirror_export/release/integration_pin.json"
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
    pinned_version = config.toolchain.get("akms_version")
    if pinned_version and akms.__version__ != pinned_version:
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

    # ── Blocking: repo2md must actually be callable ───────────────────────
    command = _resolve_command(tuple(config.toolchain["repo2md_command"]))
    contract = _run(
        [*command, "export-akms", "--help"],
        cwd=root,
        timeout=float(config.toolchain["timeout_seconds"]),
    )
    contract_text = contract.stdout + contract.stderr
    if contract.returncode != 0 or any(
        flag not in contract_text for flag in ("--output", "--phase", "--json")
    ):
        raise FailureMemoryError(
            "repo2md export-akms CLI contract is unavailable", code="repo2md_contract"
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
        note("repo2md_root_unresolved", f"Cannot resolve configured repo2md root: {exc}")

    if tool_root is not None and editable_root is not None and tool_root != editable_root:
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
        if checkout_version and checkout_version != expected_version:
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
        "status": "ok",
        "advisories": advisories,
        "akms": {
            "version": akms.__version__,
            "schema": akms.AKMS_SCHEMA_VERSION,
            "public_api_sha256": digest,
        },
        "repo2md": {
            "command": list(command),
            "checkout": str(tool_root) if tool_root is not None else "",
            "version": checkout_version,
            "distribution_version": metadata_version,
            "distribution_metadata": metadata_status,
            "export_schema_version": export_schema,
            "fixture_sha256": fixture_sha,
            "commit": observed_commit,
            "dirty": observed_dirty,
        },
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
) -> dict[str, Any]:
    command = identity["repo2md"]["command"]
    mirror_config = MirrorConfig(
        provider="repo2md",
        command=command,
        timeout_seconds=float(config.toolchain["timeout_seconds"]),
        fallback_on_error=False,
        require_success=True,
        generated_at_source="request",
        selection_mode=str(config.toolchain["mirror_selection"]),
        prune=True,
        expected_export_schema_version=int(
            config.toolchain["repo2md_export_schema_version"]
        ),
        expected_akms_schema_version=str(config.toolchain["akms_schema_version"]),
    )
    request = MirrorRequest(
        repo_root=root,
        output_root=config.resolve(root, "akms_repo_root"),
        phase=phase,
        generated_at=_timestamp(generated_at),
        selection_mode=str(config.toolchain["mirror_selection"]),
        drift_check=True,
        llm_fn=None,
        prune=True,
    )
    result = run_mirror_provider(request, mirror_config, provider_name="repo2md")
    if not result.success:
        raise FailureMemoryError("repo2md mirror refresh failed", code="mirror_failure")
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
    if config.generated["routes"] == "disposable":
        candidates.append(config.resolve(root, "routes"))
    if config.generated["graph"] == "disposable":
        candidates.append(config.resolve(root, "graph"))
    if config.generated["mirror"] == "disposable":
        candidates.append(
            config.resolve(root, "akms_repo_root") / "knowledge/code-mirror"
        )
    if config.generated["loadouts"] == "disposable":
        candidates.extend(
            [
                config.resolve(root, "akms_repo_root") / "knowledge/loadouts",
                config.resolve(root, "akms_repo_root")
                / "knowledge/resolution-manifests",
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


def refresh_project(
    *,
    action: str,
    config_path: str | Path,
    repository_root: str | Path,
    global_vault: str | Path,
    phase: int = 1,
    generated_at: str | None = None,
    force_lock: bool = False,
) -> dict[str, Any]:
    """Run one refresh stage or the ordered lessons→mirror→graph chain."""
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


__all__ = ["preflight", "refresh_project", "status"]

"""mirror_provider.py — Pluggable code-mirror source projection (A2-4).

Separates mirror *orchestration* from the legacy Python AST generator.
Default provider remains ``legacy`` for backward compatibility. External
providers (e.g. repo2md) are registered by name and invoked only when
configured. Fallback to legacy is never silent: it requires
``MirrorConfig.fallback_on_error=True`` and is always recorded in the
result metadata.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Protocol, runtime_checkable

from akms.schema.models import MirrorConfig, PropagationConfig

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════
#  Errors
# ═══════════════════════════════════════════════════════════════════════


class MirrorProviderError(Exception):
    """Raised when a configured mirror provider fails hard.

    Carries a non-secret, operator-facing message. Never include argv
    secrets, tokens, or absolute home paths that would leak credentials.
    """

    def __init__(
        self,
        message: str,
        *,
        provider: str | None = None,
        code: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.code = code
        self.details = details or {}


class UnknownMirrorProviderError(MirrorProviderError):
    """Raised when the configured provider name is not registered."""

    def __init__(self, name: str, known: list[str]) -> None:
        super().__init__(
            f"Unknown mirror provider {name!r}; known: {', '.join(sorted(known)) or '(none)'}",
            provider=name,
            code="unknown_provider",
            details={"known": sorted(known)},
        )


# ═══════════════════════════════════════════════════════════════════════
#  Request / Result
# ═══════════════════════════════════════════════════════════════════════


@dataclass
class MirrorRequest:
    """Inputs to a mirror provider invocation.

    All path fields are repository-relative unless noted. Deterministic
    timestamp sources are resolved by the orchestrator before dispatch.
    """

    repo_root: Path
    phase: int
    parent_branch: str = "main"
    source_files: list[str] | None = None
    selection_mode: str = "changed"
    generated_at: datetime | None = None
    drift_check: bool = True
    llm_fn: Any = None
    # Absolute path; defaults to repo_root when None.
    output_root: Path | None = None
    # Optional git selection for external exporters.
    git_base: str | None = None
    git_head: str | None = None
    prune: bool = False
    force_lock: bool = False


@dataclass
class MirrorResult:
    """Normalized provider output matching the historical generate_mirror shape.

    Extra fields (provider, provider_metadata, errors, success, fallback_used)
    are additive so existing consumers that only read mirrors/drift_warnings
    continue to work.
    """

    mirrors: list[dict[str, Any]] = field(default_factory=list)
    drift_warnings: list[dict[str, Any]] = field(default_factory=list)
    files_processed: int = 0
    definitions_total: int = 0
    provider: str = "legacy"
    provider_metadata: dict[str, Any] = field(default_factory=dict)
    errors: list[dict[str, Any]] = field(default_factory=list)
    success: bool = True
    fallback_used: bool = False

    def to_dict(self) -> dict[str, Any]:
        """Serialize for callers expecting the pre-provider generate_mirror dict."""
        return {
            "mirrors": self.mirrors,
            "drift_warnings": self.drift_warnings,
            "files_processed": self.files_processed,
            "definitions_total": self.definitions_total,
            "provider": self.provider,
            "provider_metadata": dict(self.provider_metadata),
            "errors": list(self.errors),
            "success": self.success,
            "fallback_used": self.fallback_used,
        }


# ═══════════════════════════════════════════════════════════════════════
#  Protocol + registry
# ═══════════════════════════════════════════════════════════════════════


@runtime_checkable
class MirrorProvider(Protocol):
    """Provider of AKMS code-mirror documents."""

    name: str

    def generate(self, request: MirrorRequest, config: MirrorConfig) -> MirrorResult:
        """Produce mirrors for *request* under *config*.

        Implementations must:
        - Never use shell=True for external commands.
        - Fail before partial graph-visible output on hard errors.
        - Return non-secret metadata only (no tokens, no full argv secrets).
        """
        ...


# Factory callables registered by name. Lazy so providers can import
# heavy deps only when selected.
ProviderFactory = Callable[[], MirrorProvider]

_PROVIDER_REGISTRY: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory, *, replace: bool = False) -> None:
    """Register a provider factory under *name*.

    Raises ValueError on duplicate names unless *replace* is True.
    """
    key = name.strip().lower()
    if not key:
        raise ValueError("provider name must be non-empty")
    if key in _PROVIDER_REGISTRY and not replace:
        raise ValueError(f"mirror provider {key!r} already registered")
    _PROVIDER_REGISTRY[key] = factory


def unregister_provider(name: str) -> None:
    """Remove a provider (tests only)."""
    _PROVIDER_REGISTRY.pop(name.strip().lower(), None)


def list_providers() -> list[str]:
    """Return sorted registered provider names."""
    _ensure_builtin_providers()
    return sorted(_PROVIDER_REGISTRY)


def get_provider(name: str) -> MirrorProvider:
    """Resolve and instantiate a provider by name."""
    _ensure_builtin_providers()
    key = name.strip().lower()
    factory = _PROVIDER_REGISTRY.get(key)
    if factory is None:
        raise UnknownMirrorProviderError(key, list(_PROVIDER_REGISTRY))
    return factory()


def _ensure_builtin_providers() -> None:
    """Lazily register built-in providers (legacy + repo2md)."""
    if "legacy" not in _PROVIDER_REGISTRY:
        from akms.graph.providers.legacy import LegacyMirrorProvider

        register_provider("legacy", LegacyMirrorProvider)
    if "repo2md" not in _PROVIDER_REGISTRY:
        from akms.graph.providers.repo2md import Repo2mdMirrorProvider

        register_provider("repo2md", Repo2mdMirrorProvider)


# ═══════════════════════════════════════════════════════════════════════
#  Config helpers
# ═══════════════════════════════════════════════════════════════════════


def resolve_mirror_config(
    config: PropagationConfig | MirrorConfig | None = None,
) -> MirrorConfig:
    """Extract MirrorConfig from a PropagationConfig or pass-through."""
    if config is None:
        return MirrorConfig()
    if isinstance(config, MirrorConfig):
        return config
    mirror = getattr(config, "mirror", None)
    if isinstance(mirror, MirrorConfig):
        return mirror
    if isinstance(mirror, dict):
        return MirrorConfig(**mirror)
    return MirrorConfig()


def resolve_generated_at(
    request: MirrorRequest,
    config: MirrorConfig,
) -> datetime:
    """Resolve deterministic generation timestamp from config policy.

    Sources:
      - ``request``: use request.generated_at if set, else now (UTC)
      - ``source_date_epoch``: int seconds from SOURCE_DATE_EPOCH env
      - ``now``: wall clock UTC (legacy default)
    """
    source = (config.generated_at_source or "now").strip().lower()
    if source == "request" and request.generated_at is not None:
        return _ensure_aware(request.generated_at)
    if source == "source_date_epoch":
        raw = os.environ.get("SOURCE_DATE_EPOCH")
        if raw is None or raw == "":
            raise MirrorProviderError(
                "generated_at_source=source_date_epoch but SOURCE_DATE_EPOCH is unset",
                provider=config.provider,
                code="missing_source_date_epoch",
            )
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc)
        except (TypeError, ValueError) as exc:
            raise MirrorProviderError(
                f"Invalid SOURCE_DATE_EPOCH={raw!r}",
                provider=config.provider,
                code="invalid_source_date_epoch",
            ) from exc
    if request.generated_at is not None:
        return _ensure_aware(request.generated_at)
    return datetime.now(tz=timezone.utc)


def _ensure_aware(dt: datetime) -> datetime:
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt


def public_provider_identity(config: MirrorConfig) -> dict[str, Any]:
    """Non-secret provider identity for status/CLI surfaces."""
    return {
        "provider": config.provider,
        "fallback_on_error": config.fallback_on_error,
        "require_success": config.require_success,
        "selection_mode": config.selection_mode,
        "timeout_seconds": config.timeout_seconds,
        "command_basename": Path(config.command[0]).name if config.command else "",
        "expected_export_schema_version": config.expected_export_schema_version,
        "expected_akms_schema_version": config.expected_akms_schema_version,
    }


# ═══════════════════════════════════════════════════════════════════════
#  Dispatch
# ═══════════════════════════════════════════════════════════════════════


def run_mirror_provider(
    request: MirrorRequest,
    config: MirrorConfig | PropagationConfig | None = None,
    *,
    provider_name: str | None = None,
) -> MirrorResult:
    """Dispatch *request* to the configured provider with explicit fallback policy.

    Fallback rules:
      - Primary provider is ``provider_name`` or ``config.provider`` (default legacy).
      - On primary failure, if provider is not legacy and
        ``fallback_on_error`` is True, run legacy and mark ``fallback_used``.
      - On primary failure with ``fallback_on_error`` False, raise
        ``MirrorProviderError`` (never silent).
    """
    mirror_cfg = resolve_mirror_config(config)
    name = (provider_name or mirror_cfg.provider or "legacy").strip().lower()

    # Apply selection defaults from config when request left them unset.
    if request.selection_mode in ("", "changed") and mirror_cfg.selection_mode:
        # Only override the dataclass default when config sets a non-default.
        if request.source_files is None and mirror_cfg.selection_mode != "changed":
            request.selection_mode = mirror_cfg.selection_mode
    if not request.prune and mirror_cfg.prune:
        request.prune = True
    if not request.force_lock and mirror_cfg.force_lock:
        request.force_lock = True

    if request.generated_at is None:
        try:
            request.generated_at = resolve_generated_at(request, mirror_cfg)
        except MirrorProviderError:
            # Only fatal for non-legacy / epoch-required paths.
            if name != "legacy" and mirror_cfg.generated_at_source == "source_date_epoch":
                raise
            request.generated_at = datetime.now(tz=timezone.utc)

    provider = get_provider(name)
    try:
        result = provider.generate(request, mirror_cfg)
    except MirrorProviderError as exc:
        return _handle_provider_failure(
            exc,
            request=request,
            mirror_cfg=mirror_cfg,
            primary_name=name,
        )
    except Exception as exc:
        wrapped = MirrorProviderError(
            f"Provider {name!r} failed: {exc}",
            provider=name,
            code="provider_exception",
            details={"exception_type": type(exc).__name__},
        )
        return _handle_provider_failure(
            wrapped,
            request=request,
            mirror_cfg=mirror_cfg,
            primary_name=name,
        )

    if not result.success:
        error = MirrorProviderError(
            result.errors[0].get("message", "provider reported failure")
            if result.errors
            else f"Provider {name!r} reported success=False",
            provider=name,
            code=(result.errors[0].get("code") if result.errors else "provider_failure"),
            details={"errors": result.errors},
        )
        return _handle_provider_failure(
            error,
            request=request,
            mirror_cfg=mirror_cfg,
            primary_name=name,
        )

    result.provider = name
    return result


def _handle_provider_failure(
    error: MirrorProviderError,
    *,
    request: MirrorRequest,
    mirror_cfg: MirrorConfig,
    primary_name: str,
) -> MirrorResult:
    """Apply explicit fallback policy or re-raise."""
    can_fallback = (
        primary_name != "legacy"
        and mirror_cfg.fallback_on_error
    )
    if not can_fallback:
        logger.error(
            "Mirror provider %r failed (fallback disabled): %s",
            primary_name,
            error,
        )
        raise error

    logger.warning(
        "Mirror provider %r failed; falling back to legacy (explicit policy): %s",
        primary_name,
        error,
    )
    legacy = get_provider("legacy")
    result = legacy.generate(request, mirror_cfg)
    result.provider = "legacy"
    result.fallback_used = True
    result.provider_metadata = {
        **result.provider_metadata,
        "fallback_from": primary_name,
        "fallback_reason": str(error),
        "fallback_code": error.code,
    }
    result.errors = [
        {
            "code": error.code or "provider_failure",
            "message": str(error),
            "provider": primary_name,
            "recovered_via": "legacy",
        },
        *result.errors,
    ]
    return result


def refresh_mirror(
    repo_root: str | Path,
    phase: int,
    *,
    parent_branch: str = "main",
    source_files: list[str] | None = None,
    drift_check: bool = True,
    llm_fn: Any = None,
    config: PropagationConfig | MirrorConfig | None = None,
    provider_name: str | None = None,
    require_success: bool | None = None,
) -> dict[str, Any]:
    """High-level refresh entry used by orchestrator / CLI / MCP.

    Returns the historical generate_mirror dict shape with additive
    provider fields. When *require_success* (or config.mirror.require_success)
    is True and the provider fails without recoverable fallback, raises
    ``MirrorProviderError`` so graph rebuild can be blocked.
    """
    mirror_cfg = resolve_mirror_config(config)
    request = MirrorRequest(
        repo_root=Path(repo_root),
        phase=phase,
        parent_branch=parent_branch,
        source_files=source_files,
        selection_mode=mirror_cfg.selection_mode or "changed",
        drift_check=drift_check,
        llm_fn=llm_fn,
        prune=mirror_cfg.prune,
        force_lock=mirror_cfg.force_lock,
    )
    # Hard provider failures raise MirrorProviderError (no silent swallow).
    # ``require_success`` is applied by orchestrator callers that choose to
    # block graph rebuild; successful returns always have success=True here.
    if require_success is None:
        require_success = mirror_cfg.require_success
    result = run_mirror_provider(
        request,
        mirror_cfg,
        provider_name=provider_name,
    )
    if require_success and not result.success:
        raise MirrorProviderError(
            "mirror refresh reported success=False",
            provider=result.provider,
            code="require_success",
            details={"errors": result.errors},
        )

    out = result.to_dict()
    out["provider_identity"] = public_provider_identity(mirror_cfg)
    return out

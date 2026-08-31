"""Neutral OpenTelemetry instrumentation for AKMS.

This module is owned by the core, not by the embedded runtime: core graph,
schema, projection, and evidence modules may import it, and it imports nothing
from :mod:`akms.orchestrator`. That direction is deliberate — the runtime
depends on core contracts, never the reverse.

OpenTelemetry itself is optional. Install it with the ``telemetry`` extra::

    pip install "akms[telemetry]"

Without that extra the instrumentation degrades to no-ops: :func:`traced` is a
pass-through decorator and the span helpers yield inert spans, so core
operations run unchanged and untraced. Passive instrumentation degrading
quietly is intentional; an *explicit* call to :func:`init_telemetry` is a
direct request for a capability, so it raises instead.

Usage::

    from akms.telemetry import traced, trace_stage

    @traced("build_graph")
    def build_graph(): ...

    with trace_stage("execute", phase=phase):
        ...
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import sys
import threading
import time
from functools import wraps
from typing import Any, Callable

try:
    from opentelemetry import trace
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.sdk.trace.export import (
        BatchSpanProcessor,
        ConsoleSpanExporter,
        SimpleSpanProcessor,
    )
    from opentelemetry.semconv.resource import ResourceAttributes

    TELEMETRY_AVAILABLE = True
except ImportError:  # pragma: no cover - exercised by the minimal-core suite
    trace = None  # type: ignore[assignment]
    Resource = TracerProvider = None  # type: ignore[assignment]
    BatchSpanProcessor = ConsoleSpanExporter = SimpleSpanProcessor = None  # type: ignore[assignment]
    ResourceAttributes = None  # type: ignore[assignment]

    TELEMETRY_AVAILABLE = False

logger = logging.getLogger(__name__)

#: Message used whenever a caller explicitly asks for telemetry that is not
#: installed. Names the exact install command rather than the bare import error.
_MISSING_EXTRA = (
    "OpenTelemetry is not installed. Install the telemetry extra to enable "
    'tracing: pip install "akms[telemetry]"'
)


# ═══════════════════════════════════════════════════════════════════════
#  No-op fallbacks
# ═══════════════════════════════════════════════════════════════════════


class _NoOpSpan:
    """Inert stand-in for an OpenTelemetry span.

    Accepts and discards every span operation the AKMS call sites use, so
    instrumented code paths need no conditional branches of their own.
    """

    def set_attribute(self, key: str, value: Any) -> None:
        return None

    def record_exception(self, exception: BaseException) -> None:
        return None

    def end(self) -> None:
        return None

    def __enter__(self) -> _NoOpSpan:
        return self

    def __exit__(self, *exc_info: object) -> bool:
        return False


class _NoOpTracer:
    """Inert stand-in for an OpenTelemetry tracer."""

    def start_as_current_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()

    def start_span(self, name: str, **kwargs: Any) -> _NoOpSpan:
        return _NoOpSpan()


# ═══════════════════════════════════════════════════════════════════════
#  Setup
# ═══════════════════════════════════════════════════════════════════════

_provider: Any | None = None
_tracer: Any | None = None
_lock = threading.RLock()


def _console_export_requested() -> bool:
    """Return whether automatic initialization should export spans to console.

    Automatic telemetry must not contaminate CLI/API stdout. Console export is
    therefore opt-in via ``AKMS_TELEMETRY=console``; callers that initialize
    telemetry explicitly retain the public ``export_console`` control.
    """
    return os.getenv("AKMS_TELEMETRY", "").strip().lower() == "console"


def init_telemetry(
    service_name: str = "akms",
    export_console: bool = True,
    otlp_endpoint: str | None = None,
    span_exporter: Any | None = None,
) -> None:
    """Initialize OpenTelemetry tracing.

    Call once at runtime startup. By default, exports to console. Set
    ``otlp_endpoint`` for Jaeger, Grafana, or any OTLP-compatible backend.

    Thread-safe: guarded by module-level ``_lock``.

    Args:
        service_name: Service name for resource attribution.
        export_console: Enable console span export.
        otlp_endpoint: Optional OTLP gRPC endpoint.
        span_exporter: Injectable exporter for testing (e.g. InMemorySpanExporter).
            When provided, uses SimpleSpanProcessor for synchronous export.

    Raises:
        RuntimeError: When the ``telemetry`` extra is not installed. This is an
            explicit request for a capability, so it fails loudly rather than
            degrading to a no-op.
    """
    global _provider, _tracer

    if not TELEMETRY_AVAILABLE:
        raise RuntimeError(_MISSING_EXTRA)

    with _lock:
        resource = Resource.create(
            {
                ResourceAttributes.SERVICE_NAME: service_name,
            }
        )
        _provider = TracerProvider(resource=resource)

        if span_exporter is not None:
            # SimpleSpanProcessor makes spans available immediately (no async flush).
            _provider.add_span_processor(SimpleSpanProcessor(span_exporter))
        elif export_console:
            _provider.add_span_processor(
                BatchSpanProcessor(ConsoleSpanExporter(out=sys.stderr))
            )

        if otlp_endpoint:
            from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import (
                OTLPSpanExporter,
            )

            _provider.add_span_processor(
                BatchSpanProcessor(OTLPSpanExporter(endpoint=otlp_endpoint))
            )

        # Best-effort: register as global provider so context propagation works.
        # OTel logs a warning (not an exception) if one is already set.
        trace.set_tracer_provider(_provider)

        # Read the tracer from _provider directly so spans reach the intended
        # exporter regardless of whether set_tracer_provider took effect.
        _tracer = _provider.get_tracer("akms")
        logger.info("Telemetry initialized: service=%s", service_name)


def get_tracer() -> Any:
    """Return the AKMS tracer, auto-initializing if needed.

    Returns an inert tracer when the ``telemetry`` extra is absent, so
    instrumented core code runs untraced rather than failing.

    Thread-safe: uses double-checked locking so the fast path (tracer already
    set) is lock-free. Automatic initialization is quiet unless
    ``AKMS_TELEMETRY=console`` is set; explicit :func:`init_telemetry` calls
    keep their own ``export_console`` behavior.
    """
    if not TELEMETRY_AVAILABLE:
        return _NoOpTracer()
    if _tracer is not None:
        return _tracer
    with _lock:
        if _tracer is None:
            init_telemetry(export_console=_console_export_requested())
    return _tracer


# ═══════════════════════════════════════════════════════════════════════
#  Decorators
# ═══════════════════════════════════════════════════════════════════════


def traced(
    name: str | None = None,
    attributes: dict[str, str] | None = None,
) -> Callable:
    """Decorate a function so each call becomes an OpenTelemetry span.

    Supports both sync and async functions. Records ``akms.success``,
    ``akms.error``, and ``akms.duration_ms`` as span attributes.

    Without the ``telemetry`` extra the decorator returns the function
    unchanged, so core modules can instrument themselves unconditionally
    without taking on an optional dependency.
    """

    def decorator(func: Callable) -> Callable:
        if not TELEMETRY_AVAILABLE:
            return func

        span_name = name or f"{func.__module__}.{func.__qualname__}"

        @wraps(func)
        async def async_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                start = time.monotonic()
                try:
                    result = await func(*args, **kwargs)
                    span.set_attribute("akms.success", True)
                    return result
                except Exception as e:
                    span.set_attribute("akms.success", False)
                    span.set_attribute("akms.error", str(e))
                    span.record_exception(e)
                    raise
                finally:
                    span.set_attribute(
                        "akms.duration_ms",
                        round((time.monotonic() - start) * 1000),
                    )

        @wraps(func)
        def sync_wrapper(*args: Any, **kwargs: Any) -> Any:
            tracer = get_tracer()
            with tracer.start_as_current_span(span_name) as span:
                if attributes:
                    for k, v in attributes.items():
                        span.set_attribute(k, v)
                start = time.monotonic()
                try:
                    result = func(*args, **kwargs)
                    span.set_attribute("akms.success", True)
                    return result
                except Exception as e:
                    span.set_attribute("akms.success", False)
                    span.set_attribute("akms.error", str(e))
                    span.record_exception(e)
                    raise
                finally:
                    span.set_attribute(
                        "akms.duration_ms",
                        round((time.monotonic() - start) * 1000),
                    )

        if asyncio.iscoroutinefunction(func):
            return async_wrapper
        return sync_wrapper

    return decorator


# ═══════════════════════════════════════════════════════════════════════
#  AKMS-specific spans
# ═══════════════════════════════════════════════════════════════════════


def trace_stage(stage_name: str, phase: int = 0):
    """Return a context manager tracing one runtime stage."""
    if not TELEMETRY_AVAILABLE:
        return contextlib.nullcontext(_NoOpSpan())
    tracer = get_tracer()
    return tracer.start_as_current_span(
        f"akms.stage.{stage_name}",
        attributes={
            "akms.stage": stage_name,
            "akms.phase": phase,
        },
    )


def trace_agent_call(
    task_id: str,
    agent_role: str,
    model: str,
) -> Any:
    """Start a span for a subagent call. The caller must end it."""
    tracer = get_tracer()
    return tracer.start_span(
        f"akms.agent.{agent_role}",
        attributes={
            "akms.task_id": task_id,
            "akms.agent_role": agent_role,
            "akms.model": model,
        },
    )

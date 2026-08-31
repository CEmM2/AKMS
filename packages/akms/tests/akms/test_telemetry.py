"""Tests for AKMS telemetry instrumentation (Phase 3).

Covers:
- Telemetry initialization with configurable exporter
- Tracer retrieval and auto-initialization
- traced() decorator on sync functions
- traced() decorator on async functions
- traced() error handling and exception recording
- trace_stage() context manager with phase/stage attributes
- trace_agent_call() span helpers with task_id, agent_role, model attributes
"""

from __future__ import annotations

import asyncio
import sys
from unittest.mock import patch

import pytest
from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from akms import telemetry
from akms.telemetry import (
    get_tracer,
    init_telemetry,
    trace_agent_call,
    trace_stage,
    traced,
)


def _reset_globals():
    """Reset module-level globals before each test.

    OpenTelemetry's global TracerProvider can only be set once per process.
    We work around this by getting tracers directly from _provider rather than
    from the global registry. Resetting the module globals ensures each test
    creates a fresh TracerProvider wired to its own InMemorySpanExporter.
    """
    telemetry._provider = None
    telemetry._tracer = None


class TestInitTelemetry:
    """Tests for init_telemetry() function."""

    @pytest.mark.unit
    def test_init_with_inmemory_exporter(self):
        """Verifies: init_telemetry() initializes TracerProvider with InMemorySpanExporter.

        Acceptance criterion:
        - init_telemetry() initializes TracerProvider with configurable exporter
        """
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(
            service_name="akms-test", export_console=False, span_exporter=exporter
        )

        assert telemetry._provider is not None
        assert telemetry._tracer is not None
        exporter.clear()

    @pytest.mark.unit
    def test_init_idempotent(self):
        """Verifies: Multiple calls to init_telemetry() do not error."""
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(
            service_name="akms-test", export_console=False, span_exporter=exporter
        )
        # Second call should not raise
        init_telemetry(
            service_name="akms-test2", export_console=False, span_exporter=exporter
        )
        exporter.clear()

    @pytest.mark.unit
    def test_explicit_console_export_uses_stderr(self):
        """Explicit console telemetry must never contaminate command stdout."""
        _reset_globals()
        with (
            patch.object(telemetry, "ConsoleSpanExporter") as exporter_cls,
            patch.object(telemetry, "BatchSpanProcessor") as processor_cls,
        ):
            init_telemetry(export_console=True)

        exporter_cls.assert_called_once_with(out=sys.stderr)
        processor_cls.assert_called_once_with(exporter_cls.return_value)


class TestGetTracer:
    """Tests for get_tracer() function."""

    @pytest.mark.unit
    def test_get_tracer_returns_valid_tracer(self):
        """Verifies: get_tracer() returns a valid Tracer object.

        Acceptance criterion:
        - get_tracer() auto-initializes if needed, returns valid Tracer
        """
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)
        tracer = get_tracer()
        assert tracer is not None
        # A valid tracer can start a span
        with tracer.start_as_current_span("test-span"):
            pass
        exporter.clear()

    @pytest.mark.unit
    def test_get_tracer_auto_initializes(self):
        """Verifies: get_tracer() auto-initializes if init_telemetry() not called."""
        _reset_globals()
        # Call get_tracer without calling init_telemetry first
        tracer = get_tracer()
        assert tracer is not None
        assert telemetry._provider is not None
        assert telemetry._tracer is not None

    @pytest.mark.unit
    def test_get_tracer_auto_initializes_quietly(self, monkeypatch):
        """Automatic initialization attaches no console exporter by default."""
        _reset_globals()
        monkeypatch.delenv("AKMS_TELEMETRY", raising=False)

        with patch.object(
            telemetry, "init_telemetry", wraps=telemetry.init_telemetry
        ) as init_spy:
            get_tracer()

        init_spy.assert_called_once_with(export_console=False)

    @pytest.mark.unit
    def test_get_tracer_honors_console_opt_in(self, monkeypatch):
        """AKMS_TELEMETRY=console enables the automatic console exporter."""
        _reset_globals()
        monkeypatch.setenv("AKMS_TELEMETRY", " CoNsOlE ")

        with patch.object(
            telemetry, "init_telemetry", wraps=telemetry.init_telemetry
        ) as init_spy:
            get_tracer()

        init_spy.assert_called_once_with(export_console=True)


class TestTracedDecorator:
    """Tests for traced() decorator."""

    @pytest.mark.unit
    def test_traced_sync_function_records_success_and_duration(self):
        """Verifies: traced() decorator on sync function records success + duration_ms.

        Acceptance criterion:
        - traced() decorator works on sync functions (records success, duration_ms)
        """
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        @traced("test.sync.success")
        def my_func():
            return "hello"

        result = my_func()
        assert result == "hello"

        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        span = next(s for s in spans if s.name == "test.sync.success")
        attrs = span.attributes
        assert attrs["akms.success"] is True
        assert attrs["akms.duration_ms"] >= 0
        exporter.clear()

    @pytest.mark.unit
    def test_traced_sync_function_with_custom_attributes(self):
        """Verifies: traced() decorator passes custom span attributes on sync function."""
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        @traced("test.sync.custom", attributes={"component": "graph", "version": "2"})
        def my_func():
            return 99

        result = my_func()
        assert result == 99

        spans = exporter.get_finished_spans()
        span = next(s for s in spans if s.name == "test.sync.custom")
        assert span.attributes["component"] == "graph"
        assert span.attributes["version"] == "2"
        exporter.clear()

    @pytest.mark.unit
    def test_traced_async_function_records_success_and_duration(self):
        """Verifies: traced() decorator on async function records success + duration_ms.

        Acceptance criterion:
        - traced() decorator works on async functions (records success, duration_ms)
        """
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        @traced("test.async.success")
        async def my_async_func():
            return "async-result"

        result = asyncio.run(my_async_func())
        assert result == "async-result"

        spans = exporter.get_finished_spans()
        assert len(spans) >= 1
        span = next(s for s in spans if s.name == "test.async.success")
        attrs = span.attributes
        assert attrs["akms.success"] is True
        assert attrs["akms.duration_ms"] >= 0
        exporter.clear()

    @pytest.mark.unit
    def test_traced_async_function_with_custom_attributes(self):
        """Verifies: traced() decorator passes custom span attributes on async function."""
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        @traced("test.async.custom", attributes={"env": "test"})
        async def my_async_func():
            return True

        asyncio.run(my_async_func())

        spans = exporter.get_finished_spans()
        span = next(s for s in spans if s.name == "test.async.custom")
        assert span.attributes["env"] == "test"
        exporter.clear()

    @pytest.mark.unit
    def test_traced_function_records_error_on_exception(self):
        """Verifies: traced() decorator records akms.error and exception on failure.

        Acceptance criterion:
        - traced() records akms.error and exception on failure
        """
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        @traced("test.sync.error")
        def failing_func():
            raise ValueError("something went wrong")

        with pytest.raises(ValueError):
            failing_func()

        spans = exporter.get_finished_spans()
        span = next(s for s in spans if s.name == "test.sync.error")
        attrs = span.attributes
        assert attrs["akms.success"] is False
        assert "something went wrong" in attrs["akms.error"]
        exporter.clear()

    @pytest.mark.unit
    def test_traced_function_reraises_exception(self):
        """Verifies: traced() decorator reraises exception after recording."""
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        @traced("test.sync.reraise")
        def failing_func():
            raise RuntimeError("must propagate")

        with pytest.raises(RuntimeError, match="must propagate"):
            failing_func()

        exporter.clear()


class TestTraceStage:
    """Tests for trace_stage() context manager."""

    @pytest.mark.unit
    def test_trace_stage_sets_attributes(self):
        """Verifies: trace_stage() context manager sets akms.stage and akms.phase attributes.

        Acceptance criterion:
        - trace_stage() returns context manager with akms.stage and akms.phase attributes
        """
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        with trace_stage("execute", phase=3):
            pass

        spans = exporter.get_finished_spans()
        span = next(s for s in spans if s.name == "akms.stage.execute")
        assert span.attributes["akms.stage"] == "execute"
        assert span.attributes["akms.phase"] == 3
        exporter.clear()

    @pytest.mark.unit
    def test_trace_stage_nests_correctly(self):
        """Verifies: trace_stage() nests correctly within another span."""
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        with trace_stage("outer", phase=1):
            with trace_stage("inner", phase=2):
                pass

        spans = exporter.get_finished_spans()
        names = {s.name for s in spans}
        assert "akms.stage.outer" in names
        assert "akms.stage.inner" in names
        exporter.clear()

    @pytest.mark.unit
    def test_trace_stage_records_duration(self):
        """Verifies: trace_stage() records span duration."""
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        with trace_stage("timed-stage", phase=0):
            pass

        spans = exporter.get_finished_spans()
        span = next(s for s in spans if s.name == "akms.stage.timed-stage")
        # Span has start and end time (nanoseconds)
        assert span.start_time is not None
        assert span.end_time is not None
        assert span.end_time >= span.start_time
        exporter.clear()


class TestTraceAgentCall:
    """Tests for trace_agent_call() span helper."""

    @pytest.mark.unit
    def test_trace_agent_call_sets_attributes(self):
        """Verifies: trace_agent_call() span sets akms.task_id, akms.agent_role, akms.model attributes.

        Acceptance criterion:
        - trace_agent_call() returns span with akms.task_id, akms.agent_role, akms.model attributes
        """
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        span = trace_agent_call(
            task_id="task-42",
            agent_role="implementer",
            model="claude-sonnet-4-5",
        )
        span.end()

        spans = exporter.get_finished_spans()
        finished = next(s for s in spans if s.name == "akms.agent.implementer")
        assert finished.attributes["akms.task_id"] == "task-42"
        assert finished.attributes["akms.agent_role"] == "implementer"
        assert finished.attributes["akms.model"] == "claude-sonnet-4-5"
        exporter.clear()

    @pytest.mark.unit
    def test_trace_agent_call_with_optional_attributes(self):
        """Verifies: trace_agent_call() handles optional attributes gracefully."""
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        span = trace_agent_call(
            task_id="task-99",
            agent_role="code_reviewer",
            model="claude-haiku-3-5",
        )
        span.end()

        spans = exporter.get_finished_spans()
        finished = next(s for s in spans if s.name == "akms.agent.code_reviewer")
        assert finished.attributes["akms.task_id"] == "task-99"
        exporter.clear()

    @pytest.mark.unit
    def test_trace_agent_call_nests_correctly(self):
        """Verifies: trace_agent_call() nests correctly within trace_stage()."""
        _reset_globals()
        exporter = InMemorySpanExporter()
        init_telemetry(export_console=False, span_exporter=exporter)

        with trace_stage("dispatch", phase=2):
            agent_span = trace_agent_call(
                task_id="task-1",
                agent_role="physics_reviewer",
                model="claude-opus-4",
            )
            agent_span.end()

        spans = exporter.get_finished_spans()
        names = {s.name for s in spans}
        assert "akms.stage.dispatch" in names
        assert "akms.agent.physics_reviewer" in names
        exporter.clear()

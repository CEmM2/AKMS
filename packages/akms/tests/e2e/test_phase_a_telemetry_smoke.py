"""Phase A E2E: telemetry initialization and span capture."""

from opentelemetry.sdk.trace.export.in_memory_span_exporter import InMemorySpanExporter

from akms import telemetry
from akms.telemetry import init_telemetry, traced


def test_telemetry_emits_spans():
    """Full init → traced function → verify span exists."""
    # Reset global state
    telemetry._provider = None
    telemetry._tracer = None

    exporter = InMemorySpanExporter()
    init_telemetry(
        service_name="akms-test", export_console=False, span_exporter=exporter
    )

    @traced("test.smoke")
    def dummy():
        return 42

    result = dummy()
    assert result == 42

    # Spans are synchronous with SimpleSpanProcessor — no flush needed.
    spans = exporter.get_finished_spans()
    assert len(spans) >= 1
    assert any(s.name == "test.smoke" for s in spans)
    exporter.clear()

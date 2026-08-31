"""SDK orchestrator — stage pipeline, checkpoints, agent configs, MCP tools."""

from akms.orchestrator.stages import PipelineState, Stage
from akms.telemetry import traced

# call_llm, wave_dispatch symbols, run_pipeline, and create_mcp_server are
# lazy-loaded via __getattr__ to avoid importing heavyweight modules (LiteLLM,
# OTel, agent_configs, mcp_tools, orchestrator.py) when only
# PipelineState/Stage/traced are needed.
_WAVE_DISPATCH_NAMES = frozenset({
    "TaskResult", "build_waves", "dispatch_phase", "find_blocked_tasks",
    "resolve_model_for_tier", "run_subagent", "validate_scope_disjointness",
})


def __getattr__(name: str):
    """Lazy imports — avoids heavyweight module loading and circular-import risk."""
    if name == "call_llm":
        from akms.orchestrator.llm_router import call_llm

        globals()["call_llm"] = call_llm
        return call_llm
    if name == "create_mcp_server":
        from akms.orchestrator.mcp_tools import create_mcp_server

        globals()["create_mcp_server"] = create_mcp_server
        return create_mcp_server
    if name == "run_pipeline":
        from akms.orchestrator.orchestrator import run_pipeline

        globals()["run_pipeline"] = run_pipeline
        return run_pipeline
    if name in _WAVE_DISPATCH_NAMES:
        from akms.orchestrator import wave_dispatch as _wd

        for _n in _WAVE_DISPATCH_NAMES:
            globals()[_n] = getattr(_wd, _n)
        return globals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "PipelineState",
    "Stage",
    "TaskResult",
    "build_waves",
    "call_llm",
    "create_mcp_server",
    "dispatch_phase",
    "find_blocked_tasks",
    "resolve_model_for_tier",
    "run_pipeline",
    "run_subagent",
    "traced",
    "validate_scope_disjointness",
]

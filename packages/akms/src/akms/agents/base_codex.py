"""AKMS Codex runtime adapter (OpenAI Agents SDK).

Runtime contract:
- ``AKMSCodexAgent`` subclasses :class:`akms.agents.base.AKMSAgent` and only
  overrides ``execute()``.
- ``AKMSAgent.run()`` remains the sealed protocol owner for loadout parsing,
  system prompt assembly, and post-execution AgentMemory validation.
- The agent running inside ``execute()`` writes its own AgentMemory file,
  per the instructions in the system prompt.  ``run()`` reads it back from
  disk and validates it.
- Runtime selection is explicit: AKMS continues to default to
  ``AKMSAgent`` (Claude). Codex is opt-in via class path override, e.g.
  ``--agent akms.agents.base_codex.AKMSCodexAgent``.
- Tool affordance parity expectation for the codex runtime: ``Read``, ``Write``,
  ``Edit``, ``MultiEdit``, ``Glob``, ``Grep``, and ``Bash`` with repository-root
  scoping when ``repo_root`` is provided.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from akms.agents.base import AKMSAgent, Loadout


class AKMSCodexAgent(AKMSAgent):
    """Codex/OpenAI runtime variant of ``AKMSAgent``.

    Overrides ``execute()`` to use the OpenAI Agents SDK while
    preserving the sealed ``run()`` protocol.  The agent is instructed
    (via the system prompt) to write its own AgentMemory file.
    """

    async def execute(
        self,
        task_json: dict,
        loadout: Loadout,
        system_prompt: str,
    ) -> None:
        """Execute using the OpenAI Agents SDK.

        The agent receives the system_prompt (including AgentMemory write
        instructions) and the task prompt.  It writes AgentMemory to disk
        as part of its work.  Returns None.
        """
        user_message = self._build_task_prompt(task_json)
        await _codex_sdk_execute(
            user_message, loadout, system_prompt, self.model, self.repo_root,
            allowed_tools=self._resolve_allowed_tools(task_json),
        )


async def _codex_sdk_execute(
    user_message: str,
    loadout: Loadout,
    system_prompt: str,
    model: str,
    repo_root: Path,
    allowed_tools: list[str] | None = None,
) -> None:
    """Run the Codex runtime.  The agent writes AgentMemory to disk.

    ``allowed_tools`` is the concrete SDK-level tool-name list computed by
    ``AKMSAgent._resolve_allowed_tools``. Only @function_tool bindings whose
    name appears in this list are registered with the Agent. When None is
    passed, the legacy baseline set is used (Grep is intentionally excluded
    per FR-C05).
    """
    try:
        from agents import Agent, Runner, function_tool
    except ImportError as exc:
        raise ImportError(
            "The 'openai-agents' package is required for AKMSCodexAgent execution. "
            "Install it with: uv add openai-agents"
        ) from exc

    @function_tool(name_override="Read")
    def preflight(self) -> str | None:
        """Report backend availability: this agent drives the OpenAI Agents SDK."""
        import importlib.util

        if importlib.util.find_spec("agents") is None:
            return (
                "The Codex/local agent backends need the OpenAI Agents SDK "
                "(the 'openai-agents' package), which is not installed. "
                'Install it with: pip install "akms[agents]" (or '
                '"akms[orchestration]" for the complete embedded runtime).'
            )
        return None

    def read_tool(path: str) -> str:
        return _tool_read(repo_root, path)

    @function_tool(name_override="Write")
    def write_tool(path: str, content: str) -> str:
        return _tool_write(repo_root, path, content)

    @function_tool(name_override="Edit")
    def edit_tool(path: str, old_text: str, new_text: str) -> str:
        return _tool_edit(repo_root, path, old_text, new_text)

    # strict_mode=False: the `edits: list[dict]` parameter is a free-form object
    # array, which the OpenAI Agents SDK's strict JSON-schema builder rejects
    # ("additionalProperties should not be set"). Non-strict is the SDK's
    # sanctioned escape hatch for free-form tool inputs.
    @function_tool(name_override="MultiEdit", strict_mode=False)
    def multi_edit_tool(path: str, edits: list[dict]) -> str:
        return _tool_multi_edit(repo_root, path, edits)

    @function_tool(name_override="Glob")
    def glob_tool(pattern: str) -> str:
        return _tool_glob(repo_root, pattern)

    # No Grep binding: qmd-backed MCP tools (registered through the AKMS MCP
    # server) are the sanctioned replacement per FR-C05.

    @function_tool(name_override="Bash")
    def bash_tool(command: str) -> str:
        return _tool_bash(repo_root, command)

    # F-01b / PR18-T2: the OpenAI Agents SDK doesn't consume MCP servers
    # directly, so the AKMS search surface is registered here as
    # function tools under the same `mcp__akms__*` names the logical
    # `search` / `search_mirror` entries resolve to (see TOOL_NAME_MAP).
    # This keeps the Codex runtime at feature parity with the Claude
    # runtime's MCP-backed search, instead of silently losing tools to
    # the `n in _registry` filter.
    @function_tool(name_override="mcp__akms__akms_search_nodes")
    def search_nodes_tool(query: str, limit: int = 20) -> list[dict]:
        return _tool_search_nodes(repo_root, query, limit)

    @function_tool(name_override="mcp__akms__akms_search_sessions")
    def search_sessions_tool(query: str, limit: int = 20) -> list[dict]:
        return _tool_search_sessions(repo_root, query, limit)

    @function_tool(name_override="mcp__akms__akms_search_mirror")
    def search_mirror_tool(query: str, limit: int = 20) -> list[dict]:
        return _tool_search_mirror(repo_root, query, limit)

    @function_tool(name_override="mcp__akms__akms_get_pitfalls")
    def get_pitfalls_tool(node_ids: list[str]) -> list[dict]:
        return _tool_get_pitfalls(repo_root, node_ids)

    _registry = {
        "Read": read_tool,
        "Write": write_tool,
        "Edit": edit_tool,
        "MultiEdit": multi_edit_tool,
        "Glob": glob_tool,
        "Bash": bash_tool,
        "mcp__akms__akms_search_nodes": search_nodes_tool,
        "mcp__akms__akms_search_sessions": search_sessions_tool,
        "mcp__akms__akms_search_mirror": search_mirror_tool,
        "mcp__akms__akms_get_pitfalls": get_pitfalls_tool,
    }
    if allowed_tools is None:
        selected_names = ["Read", "Write", "Edit", "MultiEdit", "Glob", "Bash"]
    else:
        selected_names = [n for n in allowed_tools if n in _registry]

    selected = [_registry[n] for n in selected_names]

    agent = Agent(
        name="AKMSCodexAgent",
        model=model,
        instructions=system_prompt,
        tools=selected,
    )
    run_result = await Runner.run(agent, input=user_message, max_turns=25)

    # No return value — the agent writes AgentMemory to disk as part
    # of its work.  run() validates it afterward.


def _resolve_path(repo_root: Path | None, raw_path: str) -> Path:
    """Resolve and optionally scope a path to repo root."""
    candidate = Path(raw_path)
    if repo_root is not None:
        root = repo_root.resolve()
        resolved = (root / candidate).resolve() if not candidate.is_absolute() else candidate.resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(f"Path '{raw_path}' is outside repository root") from exc
        return resolved

    return candidate.resolve()


def _tool_read(repo_root: Path | None, path: str) -> str:
    try:
        resolved = _resolve_path(repo_root, path)
        return resolved.read_text(encoding="utf-8")
    except Exception as exc:
        return f"ERROR: Read failed for '{path}': {exc}"


def _tool_write(repo_root: Path | None, path: str, content: str) -> str:
    """Write tool — creates or overwrites a file."""
    try:
        resolved = _resolve_path(repo_root, path)
        resolved.parent.mkdir(parents=True, exist_ok=True)
        resolved.write_text(content, encoding="utf-8")
        return f"OK: Wrote '{path}'"
    except Exception as exc:
        return f"ERROR: Write failed for '{path}': {exc}"


def _tool_edit(repo_root: Path | None, path: str, old_text: str, new_text: str) -> str:
    try:
        resolved = _resolve_path(repo_root, path)
        source = resolved.read_text(encoding="utf-8")

        count = source.count(old_text)
        if count == 0:
            return f"ERROR: Edit failed for '{path}': old_text not found"
        if count > 1:
            return f"ERROR: Edit failed for '{path}': old_text matched {count} locations"

        updated = source.replace(old_text, new_text, 1)
        resolved.write_text(updated, encoding="utf-8")
        return f"OK: Edited '{path}'"
    except Exception as exc:
        return f"ERROR: Edit failed for '{path}': {exc}"


def _tool_multi_edit(repo_root: Path | None, path: str, edits: list[dict]) -> str:
    """Apply multiple sequential edits to a file.

    Each edit dict must have ``old_text`` and ``new_text`` keys.  Edits are
    applied in order; each edit validates that ``old_text`` is non-empty and
    appears exactly once in the *current* (already-modified) content before
    replacing it.  The file is written once after all edits succeed.

    Returns ``"OK: Applied N edits to '<path>'"`` on success, or
    ``"ERROR: ..."`` on the first validation failure (no file is written).
    """
    try:
        resolved = _resolve_path(repo_root, path)
        content = resolved.read_text(encoding="utf-8")

        for i, edit in enumerate(edits):
            old_text = edit.get("old_text", "")
            new_text = edit.get("new_text", "")

            if not old_text:
                return f"ERROR: MultiEdit failed for '{path}': edit {i} has empty old_text"

            count = content.count(old_text)
            if count == 0:
                return f"ERROR: MultiEdit failed for '{path}': edit {i} old_text not found"
            if count > 1:
                return (
                    f"ERROR: MultiEdit failed for '{path}': "
                    f"edit {i} old_text matched {count} locations"
                )

            content = content.replace(old_text, new_text, 1)

        resolved.write_text(content, encoding="utf-8")
        return f"OK: Applied {len(edits)} edits to '{path}'"
    except Exception as exc:
        return f"ERROR: MultiEdit failed for '{path}': {exc}"


def _tool_glob(repo_root: Path | None, pattern: str) -> str:
    try:
        base = repo_root.resolve() if repo_root is not None else Path.cwd()
        matches = sorted(str(p.relative_to(base)) for p in base.glob(pattern) if p.exists())
        return "\n".join(matches)
    except Exception as exc:
        return f"ERROR: Glob failed for '{pattern}': {exc}"


def _tool_bash(repo_root: Path | None, command: str) -> str:
    try:
        cwd = repo_root.resolve() if repo_root is not None else Path.cwd()
        proc = subprocess.run(
            command,
            cwd=cwd,
            shell=True,
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
        output = (proc.stdout or "") + (("\n" + proc.stderr) if proc.stderr else "")
        output = output.strip()
        if proc.returncode != 0:
            return f"ERROR: Bash command failed with exit code {proc.returncode}\n{output}".strip()
        return output
    except Exception as exc:
        return f"ERROR: Bash failed: {exc}"


# ── Codex-side implementations of the MCP search surface ────────────────
#
# PR18-T2: the Claude runtime reaches these via the MCP server registered
# on ClaudeAgentOptions. The OpenAI Agents SDK doesn't consume MCP
# servers, so we re-implement the same four tools as function tools that
# shell out to the shared `qmd_shell.run_qmd` helper — the same code
# path the MCP server itself uses.


def _tool_search_nodes(repo_root: Path | None, query: str, limit: int = 20) -> list[dict]:
    from akms.orchestrator.qmd_shell import run_qmd
    return run_qmd(
        "search_nodes", query,
        repo_root=repo_root if repo_root is not None else Path.cwd(),
    )[: max(1, int(limit))]


def _tool_search_sessions(repo_root: Path | None, query: str, limit: int = 20) -> list[dict]:
    from akms.orchestrator.qmd_shell import run_qmd
    return run_qmd(
        "search_sessions", query,
        repo_root=repo_root if repo_root is not None else Path.cwd(),
    )[: max(1, int(limit))]


def _tool_search_mirror(repo_root: Path | None, query: str, limit: int = 20) -> list[dict]:
    from akms.orchestrator.qmd_shell import run_qmd
    return run_qmd(
        "search_mirror", query,
        repo_root=repo_root if repo_root is not None else Path.cwd(),
    )[: max(1, int(limit))]


def _tool_get_pitfalls(repo_root: Path | None, node_ids: list[str]) -> list[dict]:
    """Return pitfall edges whose ``from`` node is in ``node_ids``.

    Reads ``knowledge/graph/local_state.yaml`` directly (no shell-out —
    this is structural graph data). Mirrors the MCP tool of the same
    name so Codex and Claude agents return equivalent shapes.
    """
    import yaml as _yaml
    root = repo_root.resolve() if repo_root is not None else Path.cwd()
    overlay_path = root / "knowledge" / "graph" / "local_state.yaml"
    if not overlay_path.exists():
        return []
    try:
        overlay = _yaml.safe_load(overlay_path.read_text(encoding="utf-8")) or {}
    except Exception:
        return []
    local_edges = overlay.get("local_edges") or []
    node_set = {str(n) for n in node_ids}
    hits: list[dict] = []
    for edge in local_edges:
        if not isinstance(edge, dict):
            continue
        if edge.get("type") != "pitfall":
            continue
        src = str(edge.get("from", ""))
        if node_set and src not in node_set:
            continue
        hits.append({
            "from": src,
            "to": str(edge.get("to", "")),
            "type": "pitfall",
            "weight": float(edge.get("weight", 0.5) or 0.5),
            "note": str(edge.get("note", "")),
            "source_id": str(edge.get("source_id", "")),
        })
    return hits

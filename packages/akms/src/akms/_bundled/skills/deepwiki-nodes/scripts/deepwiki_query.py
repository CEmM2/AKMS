#!/usr/bin/env python3
"""
DeepWiki Evaluation Engine

Parses a structured markdown question file, executes queries against the
DeepWiki MCP server via HTTP, and produces an output file with responses
injected below each query.

Usage:
    python deepwiki_query.py <question_file> [output_file]
    python deepwiki_query.py --discover [--endpoint URL]

If output_file is omitted, responses are appended/injected into question_file.
"""

from __future__ import annotations

import argparse
import asyncio
import hashlib
import json
import re
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

try:
    import httpx
except ImportError:
    print(
        "ERROR: httpx is required.\n"
        "Install with: uv add httpx",
        file=sys.stderr,
    )
    sys.exit(1)

try:
    import yaml
except ImportError:
    # Fallback: minimal YAML frontmatter parsing without PyYAML
    yaml = None  # type: ignore[assignment]


# ─── Data Model ───────────────────────────────────────────────────────────────


@dataclass
class Query:
    """A single DeepWiki MCP query extracted from the question file."""

    tool: str
    title: str  # Human-readable query title
    body: str  # Question text or topic hint
    heading_line: int  # Line number of the ### heading (0-indexed)
    body_start: int  # First line of body text
    body_end: int  # Last line of body text (exclusive)
    response: str | None = None
    status: str = "pending"
    elapsed: float = 0.0
    response_len: int = 0


@dataclass
class Topic:
    """An evaluation topic containing queries, ground truth, and scoring."""

    title: str
    topic_id: str
    heading_line: int
    queries: list[Query] = field(default_factory=list)


@dataclass
class EvalConfig:
    """Frontmatter configuration."""

    repo: str
    mcp_endpoint: str
    eval_name: str
    proceed_threshold: float = 3.0
    supplement_threshold: float = 2.0
    auth_token: str = ""  # Bearer token for authenticated endpoints (e.g. Devin MCP)
    org_id: str = ""  # Organization ID for Devin MCP (from Settings > Service Users)
    response_format: str = ""  # Optional format suffix appended to every ask_question body


@dataclass
class EndpointSchema:
    """Discovered MCP endpoint tool schemas."""

    tools: dict[str, dict]  # tool_name → inputSchema
    repo_param: str = "repo_name"  # detected: "repo_name" or "repoName"
    topic_param: str = "topic"  # for read_wiki_contents


# ─── Frontmatter Parsing ─────────────────────────────────────────────────────


def parse_frontmatter(text: str) -> tuple[dict, str]:
    """Extract YAML frontmatter and remaining content from markdown."""
    if not text.startswith("---"):
        return {}, text

    end = text.find("\n---", 3)
    if end == -1:
        return {}, text

    fm_text = text[3:end].strip()
    body = text[end + 4 :].lstrip("\n")

    if yaml is not None:
        fm = yaml.safe_load(fm_text)
    else:
        # Minimal manual parse for the fields we need
        fm = _manual_parse_frontmatter(fm_text)

    return fm or {}, body


def _manual_parse_frontmatter(text: str) -> dict:
    """Fallback frontmatter parser when PyYAML is unavailable."""
    result: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if ":" in line:
            key, _, val = line.partition(":")
            key = key.strip()
            val = val.strip().strip('"').strip("'")
            if val:
                # Try numeric
                try:
                    val = float(val)  # type: ignore[assignment]
                except ValueError:
                    pass
                result[key] = val
    return result


def load_config(fm: dict) -> EvalConfig:
    """Build EvalConfig from frontmatter dict."""
    thresholds = fm.get("thresholds", {})
    if not isinstance(thresholds, dict):
        thresholds = {}

    repo = fm.get("repo", "")
    if not repo:
        print("ERROR: frontmatter must include 'repo: owner/name'", file=sys.stderr)
        sys.exit(1)

    return EvalConfig(
        repo=repo,
        mcp_endpoint=fm.get("mcp_endpoint", "https://mcp.deepwiki.com/mcp"),
        eval_name=fm.get("eval_name", "DeepWiki Evaluation"),
        proceed_threshold=float(thresholds.get("proceed", 3.0)),
        supplement_threshold=float(thresholds.get("supplement", 2.0)),
        auth_token=fm.get("auth_token", ""),
        org_id=fm.get("org_id", ""),
        response_format=fm.get("response_format", ""),
    )


# ─── Question File Parsing ────────────────────────────────────────────────────

TOPIC_RE = re.compile(r"^##\s+Topic:\s*(.+)$")
QUERY_RE = re.compile(r"^###\s+\[(\w+)\]\s*(.+)$")
GROUND_TRUTH_RE = re.compile(r"^###\s+Ground\s+Truth\s*$", re.IGNORECASE)
SCORING_RE = re.compile(r"^###\s+Scoring\s*$", re.IGNORECASE)
RESPONSE_RE = re.compile(r"^####\s+Response\s*$", re.IGNORECASE)
HEADING_RE = re.compile(r"^(#{1,4})\s+")


def parse_questions(lines: list[str]) -> list[Topic]:
    """Parse the markdown body (after frontmatter) into Topics with Queries."""
    topics: list[Topic] = []
    current_topic: Topic | None = None
    current_query: Query | None = None
    i = 0

    while i < len(lines):
        line = lines[i]
        stripped = line.rstrip()

        # Check for topic heading
        m_topic = TOPIC_RE.match(stripped)
        if m_topic:
            _close_query_body(current_query, i, lines)
            title = m_topic.group(1).strip()
            topic_id = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")
            current_topic = Topic(title=title, topic_id=topic_id, heading_line=i)
            topics.append(current_topic)
            current_query = None
            i += 1
            continue

        # Check for query heading
        m_query = QUERY_RE.match(stripped)
        if m_query and current_topic is not None:
            _close_query_body(current_query, i, lines)
            tool = m_query.group(1).strip()
            title = m_query.group(2).strip()
            current_query = Query(
                tool=tool,
                title=title,
                body="",
                heading_line=i,
                body_start=i + 1,
                body_end=i + 1,
            )
            current_topic.queries.append(current_query)
            i += 1
            continue

        # Check for section boundaries that close query body
        if (
            GROUND_TRUTH_RE.match(stripped)
            or SCORING_RE.match(stripped)
            or RESPONSE_RE.match(stripped)
        ):
            _close_query_body(current_query, i, lines)
            current_query = None
            # Skip past response blocks (for idempotent re-runs)
            if RESPONSE_RE.match(stripped):
                i = _skip_response_block(i, lines)
                continue
            i += 1
            continue

        # Check for any heading that isn't a query — closes current query body
        m_heading = HEADING_RE.match(stripped)
        if m_heading and current_query is not None:
            _close_query_body(current_query, i, lines)
            current_query = None
            i += 1
            continue

        i += 1

    # Close final query
    _close_query_body(current_query, len(lines), lines)

    return topics


def _close_query_body(query: Query | None, end_line: int, lines: list[str]) -> None:
    """Finalize a query's body text from the line range."""
    if query is None:
        return
    query.body_end = end_line
    body_lines = lines[query.body_start : query.body_end]
    query.body = "\n".join(l.rstrip() for l in body_lines).strip()


def _skip_response_block(start: int, lines: list[str]) -> int:
    """Skip past a #### Response block including its code fence."""
    i = start + 1
    in_fence = False
    while i < len(lines):
        stripped = lines[i].rstrip()
        if stripped.startswith("```"):
            if in_fence:
                return i + 1  # End of fenced block = end of response
            in_fence = True
        elif not in_fence and HEADING_RE.match(stripped):
            return i  # Next heading = end of response
        i += 1
    return i


# ─── MCP HTTP Client ─────────────────────────────────────────────────────────

# Default MCP request headers.  The official DeepWiki endpoint at
# mcp.deepwiki.com/mcp uses Streamable HTTP (the current MCP transport).
# We request a plain JSON response (no streaming) so httpx can parse it
# in one shot.  If the server returns an SSE stream instead, we fall back
# to reading the stream and extracting the final JSON-RPC message.
def _build_headers(auth_token: str = "", org_id: str = "") -> dict[str, str]:
    """Build MCP request headers, optionally with Bearer auth and org ID."""
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/json, text/event-stream",
    }
    if auth_token:
        headers["Authorization"] = f"Bearer {auth_token}"
    if org_id:
        headers["X-Devin-Organization"] = org_id
    return headers


async def call_mcp(
    client: httpx.AsyncClient,
    endpoint: str,
    tool_name: str,
    arguments: dict,
    timeout: float = 120.0,
    auth_token: str = "",
    org_id: str = "",
) -> tuple[str, str]:
    """
    Call a DeepWiki MCP tool via HTTP JSON-RPC.

    Handles both plain JSON responses and SSE (text/event-stream) responses
    from Streamable HTTP endpoints.

    Returns (response_text, status) where status is "success" or "error".
    """
    call_id = hashlib.md5(
        json.dumps({"tool": tool_name, **arguments}, sort_keys=True).encode()
    ).hexdigest()[:8]

    payload = {
        "jsonrpc": "2.0",
        "id": call_id,
        "method": "tools/call",
        "params": {
            "name": tool_name,
            "arguments": arguments,
        },
    }

    try:
        headers = _build_headers(auth_token, org_id)
        resp = await client.post(
            endpoint, json=payload, headers=headers, timeout=timeout
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")

        if "text/event-stream" in content_type:
            # SSE response — parse the stream for the final JSON-RPC result
            data = _parse_sse_response(resp.text)
        else:
            # Plain JSON response
            data = resp.json()

        # Extract text from JSON-RPC response
        result = data.get("result", data)

        # Check for JSON-RPC error
        if "error" in data and isinstance(data["error"], dict):
            err = data["error"]
            msg = err.get("message", str(err))
            return f"ERROR: JSON-RPC error: {msg}", "error"

        return _extract_text(result), "success"

    except httpx.TimeoutException:
        return f"ERROR: Request timed out after {timeout}s", "timeout"
    except httpx.HTTPStatusError as e:
        return f"ERROR: HTTP {e.response.status_code}: {e.response.text[:500]}", "error"
    except Exception as e:
        return f"ERROR: {type(e).__name__}: {e}", "error"


def _parse_sse_response(text: str) -> dict:
    """
    Parse an SSE (text/event-stream) response body.

    Looks for `data:` lines containing JSON-RPC messages and returns the
    last one that contains a `result` or `error` field (the final response).
    """
    last_data: dict = {}
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("data:"):
            json_str = line[5:].strip()
            if not json_str:
                continue
            try:
                parsed = json.loads(json_str)
                if isinstance(parsed, dict):
                    if "result" in parsed or "error" in parsed:
                        last_data = parsed
                    elif not last_data:
                        last_data = parsed
            except json.JSONDecodeError:
                continue
    return last_data


def _extract_text(obj: object) -> str:
    """Recursively extract text content from an MCP response."""
    if isinstance(obj, str):
        return obj
    if isinstance(obj, dict):
        # MCP tool result format
        if "content" in obj and isinstance(obj["content"], list):
            parts = []
            for item in obj["content"]:
                if isinstance(item, dict) and item.get("type") == "text":
                    parts.append(item.get("text", ""))
            if parts:
                return "\n".join(parts)
        # JSON-RPC result wrapper
        if "result" in obj:
            return _extract_text(obj["result"])
        return json.dumps(obj, indent=2, ensure_ascii=False)
    if isinstance(obj, list):
        parts = [_extract_text(item) for item in obj]
        return "\n".join(p for p in parts if p)
    return str(obj)


# ─── Schema Discovery ────────────────────────────────────────────────────────


async def discover_endpoint(endpoint: str, auth_token: str = "", org_id: str = "") -> EndpointSchema:
    """
    Query the MCP endpoint for its tool list and parameter schemas.

    Sends `tools/list` JSON-RPC call and parses the response to determine
    the exact parameter names used by each tool.
    """
    payload = {
        "jsonrpc": "2.0",
        "id": "discover",
        "method": "tools/list",
        "params": {},
    }

    headers = _build_headers(auth_token, org_id)
    async with httpx.AsyncClient() as client:
        resp = await client.post(
            endpoint, json=payload, headers=headers, timeout=30.0
        )
        resp.raise_for_status()

        content_type = resp.headers.get("content-type", "")
        if "text/event-stream" in content_type:
            data = _parse_sse_response(resp.text)
        else:
            data = resp.json()

    tools_raw = data.get("result", {}).get("tools", [])
    if not tools_raw:
        # Try alternate structure
        tools_raw = data.get("tools", [])

    tools: dict[str, dict] = {}
    for t in tools_raw:
        name = t.get("name", "")
        schema = t.get("inputSchema", {})
        tools[name] = schema

    # Detect repo parameter name
    repo_param = "repo_name"  # default
    topic_param = "topic"  # default
    for tool_name, schema in tools.items():
        props = schema.get("properties", {})
        if "repoName" in props:
            repo_param = "repoName"
        if "repo_name" in props:
            repo_param = "repo_name"
        if tool_name == "read_wiki_contents":
            # Detect the topic/content parameter name
            for key in props:
                if key not in ("repo_name", "repoName"):
                    topic_param = key
                    break

    return EndpointSchema(
        tools=tools,
        repo_param=repo_param,
        topic_param=topic_param,
    )


def print_discovery(schema: EndpointSchema, endpoint: str) -> None:
    """Pretty-print discovered endpoint schema."""
    print(f"\n{'='*60}")
    print(f"DeepWiki MCP Endpoint Discovery")
    print(f"{'='*60}")
    print(f"Endpoint: {endpoint}")
    print(f"Tools found: {len(schema.tools)}")
    print(f"Repo parameter name: {schema.repo_param}")
    print(f"Topic parameter name: {schema.topic_param}")
    print()

    for name, input_schema in schema.tools.items():
        print(f"── {name}")
        props = input_schema.get("properties", {})
        required = input_schema.get("required", [])
        if props:
            for pname, pspec in props.items():
                req = " (required)" if pname in required else ""
                ptype = pspec.get("type", "?")
                desc = pspec.get("description", "")
                print(f"   {pname}: {ptype}{req}")
                if desc:
                    print(f"      {desc}")
        else:
            print(f"   (no schema or empty properties)")
        print()

    print(f"{'='*60}")
    print(f"Use these parameter names in your eval questions.")
    print(f"The eval engine will auto-detect on first run.\n")


def build_arguments(
    tool: str,
    body: str,
    repo: str,
    schema: EndpointSchema | None = None,
    response_format: str = "",
) -> dict:
    """Build MCP tool arguments from the query body and repo name.

    If response_format is set (from frontmatter), it is appended to every
    ask_question body so DeepWiki structures its answer consistently.
    """
    repo_key = schema.repo_param if schema else "repo_name"
    topic_key = schema.topic_param if schema else "topic"

    # Check if a tool's schema actually accepts a given parameter
    def _tool_accepts(tool_name: str, param: str) -> bool:
        if schema is None:
            return True  # No schema — optimistically include
        tool_schema = schema.tools.get(tool_name, {})
        props = tool_schema.get("properties", {})
        if not props:
            return True  # Empty schema — optimistically include
        return param in props

    args: dict = {repo_key: repo}
    if tool == "read_wiki_structure":
        pass  # Only needs repo
    elif tool == "read_wiki_contents":
        if body and _tool_accepts("read_wiki_contents", topic_key):
            args[topic_key] = body
    elif tool == "ask_question":
        question = body
        if response_format:
            question = f"{body}\n\n{response_format.strip()}"
        args["question"] = question
    else:
        question = body
        if response_format:
            question = f"{body}\n\n{response_format.strip()}"
        args["question"] = question  # Fallback: treat as ask_question
    return args


# ─── Execution ────────────────────────────────────────────────────────────────


async def run_queries(
    config: EvalConfig, topics: list[Topic], schema: EndpointSchema | None = None
) -> None:
    """Execute all queries against the DeepWiki MCP server."""
    total = sum(len(t.queries) for t in topics)
    done = 0

    print(f"\nEvaluation: {config.eval_name}")
    print(f"Repository: {config.repo}")
    print(f"Endpoint:   {config.mcp_endpoint}")
    if config.org_id:
        print(f"Org ID:     {config.org_id}")
    if schema:
        print(f"Repo param: {schema.repo_param}")
    print(f"Topics:     {len(topics)}")
    print(f"Queries:    {total}")
    if config.response_format:
        print(f"Format:     response_format active ({len(config.response_format)} chars)")
    print()

    async with httpx.AsyncClient() as client:
        for topic in topics:
            print(f"── {topic.title} ({len(topic.queries)} queries)")

            for query in topic.queries:
                done += 1
                label = f"  [{done}/{total}] [{query.tool}] {query.title}"
                print(f"{label}...", end="", flush=True)

                args = build_arguments(
                    query.tool, query.body, config.repo, schema,
                    response_format=config.response_format,
                )
                t0 = time.monotonic()
                text, status = await call_mcp(
                    client, config.mcp_endpoint, query.tool, args,
                    auth_token=config.auth_token,
                    org_id=config.org_id,
                )
                elapsed = time.monotonic() - t0

                query.response = text
                query.status = status
                query.elapsed = elapsed
                query.response_len = len(text)

                status_icon = "✓" if status == "success" else "✗"
                print(f" {status_icon} ({elapsed:.1f}s, {len(text)} chars)")

    print(f"\nDone. {done} queries executed.\n")


# ─── Output Assembly ──────────────────────────────────────────────────────────


def inject_responses(
    original_lines: list[str],
    topics: list[Topic],
    config: EvalConfig,
) -> list[str]:
    """
    Build the output by replaying original lines and injecting #### Response
    blocks after each query body. Existing response blocks are replaced.

    Returns a list of output lines.
    """
    # Build a map: line_number → query (for queries that have responses)
    query_at_line: dict[int, Query] = {}
    for topic in topics:
        for q in topic.queries:
            query_at_line[q.heading_line] = q

    # Strip existing summary section for idempotent re-runs
    summary_re = re.compile(r"^##\s+Evaluation\s+Summary\s*$", re.IGNORECASE)
    truncated_lines = []
    for ln in original_lines:
        if summary_re.match(ln.rstrip()):
            # Drop everything from here to end of file
            break
        truncated_lines.append(ln)
    # Also strip trailing blank lines / horizontal rules before the old summary
    while truncated_lines and truncated_lines[-1].strip() in ("", "---"):
        truncated_lines.pop()
    original_lines = truncated_lines

    output: list[str] = []
    i = 0
    injected_for: set[int] = set()

    while i < len(original_lines):
        line = original_lines[i]
        stripped = line.rstrip()

        # Skip existing #### Response blocks (will be re-injected)
        if RESPONSE_RE.match(stripped):
            i = _skip_response_block(i, original_lines)
            continue

        output.append(line)

        # Check if this line is a query heading — track it
        m_query = QUERY_RE.match(stripped)
        if m_query and i in query_at_line:
            q = query_at_line[i]
            # We need to emit the body lines, then inject the response
            # Body lines are from body_start to body_end
            body_end = q.body_end
            i += 1
            while i < body_end and i < len(original_lines):
                output.append(original_lines[i])
                i += 1

            # Now inject the response
            if q.response is not None:
                output.append("\n")
                output.append("#### Response\n")
                meta = (
                    f"<!-- deepwiki_query: tool={q.tool}, status={q.status}, "
                    f"chars={q.response_len}, elapsed={q.elapsed:.1f}s -->\n"
                )
                output.append(meta)
                output.append("```\n")
                for resp_line in q.response.splitlines():
                    # Escape any ``` inside the response
                    if resp_line.strip() == "```" or resp_line.strip().startswith("```"):
                        resp_line = resp_line.replace("```", "` ` `")
                    output.append(resp_line + "\n")
                output.append("```\n")
                output.append("\n")
            injected_for.add(i)
            continue

        i += 1

    # Append summary section
    output.extend(_build_summary(topics, config))

    return output


def _build_summary(topics: list[Topic], config: EvalConfig) -> list[str]:
    """Build the evaluation summary section."""
    lines: list[str] = []
    lines.append("\n---\n\n")
    lines.append("## Evaluation Summary\n\n")

    # Per-topic stats table
    lines.append("| Topic | Queries | Succeeded | Failed | Avg Response Length |\n")
    lines.append("|-------|:-------:|:---------:|:------:|:-------------------:|\n")

    total_queries = 0
    total_success = 0
    total_elapsed = 0.0

    for topic in topics:
        n = len(topic.queries)
        ok = sum(1 for q in topic.queries if q.status == "success")
        fail = n - ok
        avg_len = (
            sum(q.response_len for q in topic.queries) // max(n, 1)
        )
        total_queries += n
        total_success += ok
        total_elapsed += sum(q.elapsed for q in topic.queries)

        lines.append(
            f"| {topic.title} | {n} | {ok} | {fail} | "
            f"{avg_len:,} chars |\n"
        )

    # Metadata
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    lines.append(f"\n**Run metadata:**\n")
    lines.append(f"- Timestamp: {ts}\n")
    lines.append(f"- Repo: {config.repo}\n")
    lines.append(f"- MCP endpoint: {config.mcp_endpoint}\n")
    lines.append(f"- Total queries: {total_queries}\n")
    lines.append(f"- Succeeded: {total_success}\n")
    lines.append(f"- Failed: {total_queries - total_success}\n")
    lines.append(f"- Total elapsed: {total_elapsed:.1f}s\n")
    lines.append(
        f"- Decision thresholds: proceed={config.proceed_threshold}, "
        f"supplement={config.supplement_threshold}\n"
    )

    # Summary scorecard
    lines.append("\n### Summary Scorecard\n\n")
    lines.append("| Topic | D1 | D2 | D3 | Avg |\n")
    lines.append("|-------|:--:|:--:|:--:|:---:|\n")
    for topic in topics:
        short = topic.title.split("(")[0].split("/")[0].strip()
        lines.append(f"| {short} | | | | |\n")
    lines.append("| **Average** | | | | **Overall:** |\n")

    # Decision checkboxes
    lines.append("\n### Decision\n\n")
    lines.append(
        f"- [ ] ≥ {config.proceed_threshold} → "
        "Proceed with extraction pipeline\n"
    )
    lines.append(
        f"- [ ] {config.supplement_threshold}–{config.proceed_threshold} → "
        "Proceed with heavy supplementation\n"
    )
    lines.append(
        f"- [ ] < {config.supplement_threshold} → "
        "Abandon as primary source\n"
    )

    lines.append("\n### Qualitative Notes\n\n")
    lines.append("**Strongest area:**\n\n\n")
    lines.append("**Weakest area:**\n\n\n")
    lines.append("**Unexpected findings:**\n\n\n")
    lines.append("**Prompt refinement ideas (if proceeding):**\n\n\n")

    lines.append(
        "\n---\n\n*Generated by deepwiki-eval · "
        f"{ts}*\n"
    )

    return lines


# ─── Main ─────────────────────────────────────────────────────────────────────


def main() -> None:
    parser = argparse.ArgumentParser(
        description="DeepWiki query engine: runs a query file against DeepWiki MCP and injects the responses back",
        epilog="See references/question_format.md for the question file specification.",
    )
    parser.add_argument(
        "question_file",
        type=Path,
        nargs="?",
        default=None,
        help="Path to the query file (markdown)",
    )
    parser.add_argument(
        "output_file",
        type=Path,
        nargs="?",
        default=None,
        help="Path to write results (default: append to question file)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Parse and display queries without executing them",
    )
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Query the MCP endpoint for its tool list and parameter schemas, then exit",
    )
    parser.add_argument(
        "--endpoint",
        type=str,
        default=None,
        help="MCP endpoint URL (overrides frontmatter mcp_endpoint; default: https://mcp.deepwiki.com/mcp)",
    )
    parser.add_argument(
        "--auth",
        type=str,
        default="",
        help="Bearer token for authenticated endpoints (e.g. Devin MCP API key)",
    )
    parser.add_argument(
        "--org",
        type=str,
        default="",
        help="Organization ID for Devin MCP (from Settings > Service Users)",
    )
    args = parser.parse_args()

    # Resolve endpoint: CLI --endpoint > default
    endpoint = args.endpoint or "https://mcp.deepwiki.com/mcp"

    # ── Discovery mode ──
    if args.discover:
        print("Discovering MCP endpoint schema...")
        if args.auth:
            print(f"  Using authenticated mode (Bearer token)")
        if args.org:
            print(f"  Organization ID: {args.org}")
        try:
            schema = asyncio.run(discover_endpoint(endpoint, args.auth, args.org))
            print_discovery(schema, endpoint)
        except Exception as e:
            print(f"ERROR: Discovery failed: {type(e).__name__}: {e}", file=sys.stderr)
            sys.exit(1)
        return

    # ── Eval mode — question_file is required ──
    if args.question_file is None:
        parser.error("question_file is required (unless using --discover)")

    qf = args.question_file
    if not qf.exists():
        print(f"ERROR: Question file not found: {qf}", file=sys.stderr)
        sys.exit(1)

    text = qf.read_text(encoding="utf-8")
    fm, body = parse_frontmatter(text)
    config = load_config(fm)

    # Parse into lines for line-accurate injection
    all_lines = text.splitlines(keepends=True)

    # Find where body starts (after frontmatter)
    body_start = 0
    if text.startswith("---"):
        end_idx = text.find("\n---", 3)
        if end_idx != -1:
            # Count lines in frontmatter
            fm_text = text[: end_idx + 4]
            body_start = fm_text.count("\n")

    topics = parse_questions(all_lines)

    # Report what we found
    total_q = sum(len(t.queries) for t in topics)
    print(f"Parsed: {len(topics)} topics, {total_q} queries")
    for topic in topics:
        print(f"  {topic.title}")
        for q in topic.queries:
            body_preview = q.body[:80].replace("\n", " ")
            if len(q.body) > 80:
                body_preview += "..."
            print(f"    [{q.tool}] {q.title}: {body_preview}")

    if args.dry_run:
        print("\n(Dry run — no queries executed)")
        return

    if total_q == 0:
        print("\nNo queries found. Check the question file format.")
        print("See references/question_format.md for the specification.")
        sys.exit(1)

    # CLI --endpoint overrides frontmatter mcp_endpoint
    if args.endpoint is not None:
        config.mcp_endpoint = args.endpoint

    # CLI --auth overrides frontmatter auth_token
    if args.auth:
        config.auth_token = args.auth

    # CLI --org overrides frontmatter org_id
    if args.org:
        config.org_id = args.org

    # ── Auto-discover endpoint schema before running ──
    print(f"\nDiscovering endpoint schema at {config.mcp_endpoint}...")
    if config.auth_token:
        print(f"  Using authenticated mode (Bearer token)")
    if config.org_id:
        print(f"  Organization ID: {config.org_id}")
    schema: EndpointSchema | None = None
    try:
        schema = asyncio.run(discover_endpoint(config.mcp_endpoint, config.auth_token, config.org_id))
        print(f"  Repo param: {schema.repo_param}")
        print(f"  Topic param: {schema.topic_param}")
        print(f"  Tools: {', '.join(schema.tools.keys())}")
    except Exception as e:
        print(f"  Warning: discovery failed ({e}), using defaults (repo_name, topic)")

    # Execute queries
    asyncio.run(run_queries(config, topics, schema))

    # Build output
    output_lines = inject_responses(all_lines, topics, config)

    # Write output
    out_path = args.output_file if args.output_file else qf
    out_path.write_text("".join(output_lines), encoding="utf-8")
    print(f"Output written to: {out_path}")


if __name__ == "__main__":
    main()

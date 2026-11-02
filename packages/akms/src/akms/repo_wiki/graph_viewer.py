"""Local interactive viewer for the symbol graph written by ``repo-wiki build``.

Entry point: ``serve(graph_path, host, port, open_browser)``. Filtering lives in
``GraphStore`` and is served as JSON to a D3 page (D3 is loaded from the jsDelivr CDN).
"""

from __future__ import annotations

import json
import sys
import webbrowser
from collections import Counter, defaultdict, deque
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8765
DEFAULT_GRAPH_RELPATH = Path(".repo_wiki/generated/symbol_graph.json")

HTML = r"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8" />
  <title>Symbol Graph Viewer</title>
  <script src="https://cdn.jsdelivr.net/npm/d3@7"></script>
  <style>
    :root {
      color-scheme: dark;
      --bg: #0f172a;
      --panel: #111827;
      --panel2: #1f2937;
      --text: #e5e7eb;
      --muted: #9ca3af;
      --line: #374151;
      --accent: #93c5fd;
    }

    body {
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font-family: system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      overflow: hidden;
    }

    #toolbar {
      position: fixed;
      inset: 0 0 auto 0;
      min-height: 116px;
      background: rgba(17, 24, 39, 0.97);
      border-bottom: 1px solid var(--line);
      z-index: 10;
      padding: 12px;
      box-sizing: border-box;
      display: grid;
      grid-template-columns: repeat(8, minmax(110px, 1fr));
      gap: 10px;
      align-items: end;
    }

    label {
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 4px;
    }

    input, select, button {
      width: 100%;
      box-sizing: border-box;
      border: 1px solid #4b5563;
      border-radius: 8px;
      background: var(--panel2);
      color: var(--text);
      padding: 8px;
      font-size: 14px;
    }

    button { cursor: pointer; font-weight: 600; }
    button:hover { border-color: var(--accent); }

    #stats {
      position: fixed;
      left: 14px;
      top: 132px;
      z-index: 5;
      width: min(420px, calc(100vw - 28px));
      background: rgba(17, 24, 39, 0.94);
      border: 1px solid var(--line);
      border-radius: 12px;
      padding: 10px 12px;
      font-size: 13px;
      line-height: 1.45;
      box-sizing: border-box;
    }

    #tooltip {
      position: fixed;
      pointer-events: none;
      opacity: 0;
      z-index: 30;
      max-width: 560px;
      background: rgba(0, 0, 0, 0.88);
      color: white;
      border: 1px solid #4b5563;
      border-radius: 8px;
      padding: 8px 10px;
      font-size: 12px;
      word-break: break-word;
    }

    #status { color: var(--muted); font-size: 12px; margin-top: 4px; }

    svg {
      display: block;
      width: 100vw;
      height: 100vh;
      background: radial-gradient(circle at top left, rgba(59, 130, 246, 0.14), transparent 28rem), var(--bg);
    }

    .link { stroke-opacity: 0.55; }
    .node circle { stroke: #f9fafb; stroke-width: 0.8px; }
    .node text {
      fill: var(--text);
      font-size: 10px;
      paint-order: stroke;
      stroke: var(--bg);
      stroke-width: 3px;
      stroke-linejoin: round;
      pointer-events: none;
    }

    @media (max-width: 1100px) {
      #toolbar { grid-template-columns: repeat(4, minmax(110px, 1fr)); min-height: 210px; }
      #stats { top: 226px; }
    }
  </style>
</head>
<body>
  <div id="toolbar">
    <div><label for="typeFilter">Edge type</label><select id="typeFilter"></select></div>
    <div><label for="resolutionFilter">Resolution</label><select id="resolutionFilter"></select></div>
    <div><label for="focusInput">Focus node contains</label><input id="focusInput" list="nodeSuggestions" placeholder="Registry, Extractor, ..." /><datalist id="nodeSuggestions"></datalist></div>
    <div><label for="depthFilter">Depth</label><select id="depthFilter"><option value="0">0: focus only</option><option value="1" selected>1 hop</option><option value="2">2 hops</option><option value="3">3 hops</option><option value="4">4 hops</option><option value="5">5 hops</option></select></div>
    <div><label for="directionFilter">Direction</label><select id="directionFilter"><option value="both" selected>both</option><option value="out">outgoing</option><option value="in">incoming</option></select></div>
    <div><label for="minDegreeFilter">Min degree</label><select id="minDegreeFilter"><option value="0" selected>0</option><option value="1">1</option><option value="2">2</option><option value="3">3</option><option value="5">5</option><option value="10">10</option><option value="25">25</option><option value="50">50</option></select></div>
    <div><label for="maxDegreeFilter">Max degree</label><select id="maxDegreeFilter"><option value="0" selected>no max</option><option value="5">5</option><option value="10">10</option><option value="25">25</option><option value="50">50</option><option value="100">100</option><option value="250">250</option><option value="500">500</option></select></div>
    <div><label for="limitFilter">Node limit</label><select id="limitFilter"><option value="100">100</option><option value="250">250</option><option value="500" selected>500</option><option value="1000">1000</option><option value="2000">2000</option><option value="5000">5000</option></select></div>
    <div><label>&nbsp;</label><button id="applyBtn">Apply filters</button><div id="status"></div></div>
    <div><label>&nbsp;</label><button id="resetZoomBtn">Reset zoom</button></div>
  </div>

  <div id="stats">Loading metadata...</div>
  <div id="tooltip"></div>
  <svg></svg>

<script>
const typeFilter = document.getElementById("typeFilter");
const resolutionFilter = document.getElementById("resolutionFilter");
const focusInput = document.getElementById("focusInput");
const nodeSuggestions = document.getElementById("nodeSuggestions");
const depthFilter = document.getElementById("depthFilter");
const directionFilter = document.getElementById("directionFilter");
const minDegreeFilter = document.getElementById("minDegreeFilter");
const maxDegreeFilter = document.getElementById("maxDegreeFilter");
const limitFilter = document.getElementById("limitFilter");
const applyBtn = document.getElementById("applyBtn");
const resetZoomBtn = document.getElementById("resetZoomBtn");
const stats = document.getElementById("stats");
const statusEl = document.getElementById("status");
const tooltip = document.getElementById("tooltip");

const svg = d3.select("svg");
const width = window.innerWidth;
const height = window.innerHeight;
const zoomLayer = svg.append("g");
const zoom = d3.zoom().scaleExtent([0.03, 12]).on("zoom", event => zoomLayer.attr("transform", event.transform));
svg.call(zoom);

const edgeColor = d3.scaleOrdinal(d3.schemeTableau10);
const resolutionColor = d3.scaleOrdinal().domain(["CONFIDENT", "HEURISTIC", "UNRESOLVED", "UNKNOWN"]).range(["#22c55e", "#f59e0b", "#ef4444", "#9ca3af"]);
let simulation = null;

function fillSelect(select, values, includeAll=true) {
  select.innerHTML = "";
  if (includeAll) {
    const opt = document.createElement("option");
    opt.value = "";
    opt.textContent = "All";
    select.appendChild(opt);
  }
  for (const value of values) {
    const opt = document.createElement("option");
    opt.value = value;
    opt.textContent = value;
    select.appendChild(opt);
  }
}

function escapeHtml(value) {
  return String(value ?? "").replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;").replaceAll('"', "&quot;").replaceAll("'", "&#039;");
}

function shortLabel(value) {
  const s = String(value ?? "");
  const parts = s.split("::");
  const last = parts[parts.length - 1].split("/").pop();
  return last.length > 42 ? last.slice(0, 39) + "..." : last;
}

function queryParams() {
  const p = new URLSearchParams();
  p.set("type", typeFilter.value);
  p.set("resolution", resolutionFilter.value);
  p.set("focus", focusInput.value.trim());
  p.set("depth", depthFilter.value);
  p.set("direction", directionFilter.value);
  p.set("min_degree", minDegreeFilter.value);
  p.set("max_degree", maxDegreeFilter.value);
  p.set("limit", limitFilter.value);
  return p.toString();
}

async function loadMeta() {
  const meta = await fetch("/api/meta").then(r => r.json());
  fillSelect(typeFilter, meta.edge_types);
  fillSelect(resolutionFilter, meta.resolutions);
  stats.innerHTML = `<strong>Full graph</strong><br>Nodes: ${meta.node_count.toLocaleString()}<br>Edges: ${meta.edge_count.toLocaleString()}<br>Edge types: ${Object.entries(meta.edge_type_counts).map(([k,v]) => `${escapeHtml(k)}=${v}`).join(", ")}<br>Resolutions: ${Object.entries(meta.resolution_counts).map(([k,v]) => `${escapeHtml(k)}=${v}`).join(", ")}`;
}

let suggestionAbort = null;
focusInput.addEventListener("input", async () => {
  const q = focusInput.value.trim();
  if (q.length < 2) return;
  if (suggestionAbort) suggestionAbort.abort();
  suggestionAbort = new AbortController();
  try {
    const res = await fetch(`/api/search_nodes?q=${encodeURIComponent(q)}&limit=40`, {signal: suggestionAbort.signal});
    const data = await res.json();
    nodeSuggestions.innerHTML = "";
    for (const node of data.nodes) {
      const opt = document.createElement("option");
      opt.value = node.id;
      nodeSuggestions.appendChild(opt);
    }
  } catch (err) {
    if (err.name !== "AbortError") console.error(err);
  }
});

function drag(simulation) {
  function dragstarted(event, d) {
    if (!event.active) simulation.alphaTarget(0.25).restart();
    d.fx = d.x;
    d.fy = d.y;
  }
  function dragged(event, d) {
    d.fx = event.x;
    d.fy = event.y;
  }
  function dragended(event, d) {
    if (!event.active) simulation.alphaTarget(0);
    d.fx = null;
    d.fy = null;
  }
  return d3.drag().on("start", dragstarted).on("drag", dragged).on("end", dragended);
}

async function render() {
  statusEl.textContent = "Loading...";
  applyBtn.disabled = true;
  let graph;
  try {
    graph = await fetch(`/api/graph?${queryParams()}`).then(r => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.json();
    });
  } catch (err) {
    statusEl.textContent = "Failed.";
    stats.innerHTML = `<strong>Error</strong><br>${escapeHtml(err.message)}`;
    applyBtn.disabled = false;
    return;
  }

  statusEl.textContent = "";
  applyBtn.disabled = false;
  if (simulation) simulation.stop();
  zoomLayer.selectAll("*").remove();

  const nodes = graph.nodes.map(d => ({...d}));
  const links = graph.links.map(d => ({...d}));
  edgeColor.domain(graph.edge_types || []);

  stats.innerHTML = `<strong>Visible graph</strong><br>Nodes: ${nodes.length.toLocaleString()} / ${graph.full_node_count.toLocaleString()}<br>Edges: ${links.length.toLocaleString()} / ${graph.full_edge_count.toLocaleString()}<br>${graph.truncated ? "<strong>Limited:</strong> top nodes by degree shown.<br>" : ""}${graph.focus_resolved ? `Focus: ${escapeHtml(graph.focus_resolved)}<br>` : ""}Tip: hover, drag nodes, scroll to zoom.`;

  const link = zoomLayer.append("g").selectAll("line").data(links).join("line").attr("class", "link").attr("stroke", d => edgeColor(d.type)).attr("stroke-width", d => d.resolution === "CONFIDENT" ? 1.4 : 1.0);
  const node = zoomLayer.append("g").selectAll("g").data(nodes).join("g").attr("class", "node");

  node.append("circle").attr("r", d => Math.max(4, Math.min(15, 3 + Math.sqrt(d.degree || 1) * 1.7))).attr("fill", d => resolutionColor(d.main_resolution || "UNKNOWN"));
  node.append("text").attr("x", 9).attr("y", 3).text(d => shortLabel(d.id));

  node.on("mousemove", (event, d) => {
    tooltip.style.opacity = 1;
    tooltip.style.left = (event.clientX + 12) + "px";
    tooltip.style.top = (event.clientY + 12) + "px";
    tooltip.innerHTML = `<strong>Node</strong><br>${escapeHtml(d.id)}<br>degree: ${d.degree ?? 0}<br>in: ${d.in_degree ?? 0}, out: ${d.out_degree ?? 0}`;
  }).on("mouseleave", () => tooltip.style.opacity = 0);

  link.on("mousemove", (event, d) => {
    tooltip.style.opacity = 1;
    tooltip.style.left = (event.clientX + 12) + "px";
    tooltip.style.top = (event.clientY + 12) + "px";
    tooltip.innerHTML = `<strong>Edge</strong><br>${escapeHtml(d.source)} &rarr; ${escapeHtml(d.target)}<br>type: ${escapeHtml(d.type)}<br>resolution: ${escapeHtml(d.resolution)}<br>dst_name: ${escapeHtml(d.dst_name || "")}`;
  }).on("mouseleave", () => tooltip.style.opacity = 0);

  simulation = d3.forceSimulation(nodes)
    .force("link", d3.forceLink(links).id(d => d.id).distance(70).strength(0.35))
    .force("charge", d3.forceManyBody().strength(-110))
    .force("center", d3.forceCenter(width / 2, height / 2 + 70))
    .force("collision", d3.forceCollide().radius(d => Math.max(12, Math.min(24, 7 + Math.sqrt(d.degree || 1) * 1.2))));

  node.call(drag(simulation));

  simulation.on("tick", () => {
    link.attr("x1", d => d.source.x).attr("y1", d => d.source.y).attr("x2", d => d.target.x).attr("y2", d => d.target.y);
    node.attr("transform", d => `translate(${d.x},${d.y})`);
  });
}

applyBtn.addEventListener("click", render);
resetZoomBtn.addEventListener("click", () => svg.transition().duration(250).call(zoom.transform, d3.zoomIdentity));
loadMeta().then(render);
</script>
</body>
</html>
"""


class GraphStore:
    """In-memory edge index with the filters behind ``/api/graph``."""

    def __init__(self, edges: list[Any], source_label: str = "") -> None:
        self.source_label = source_label
        self.raw_edges: list[dict[str, Any]] = []
        self.nodes: set[str] = set()
        self.out_edges: dict[str, list[int]] = defaultdict(list)
        self.in_edges: dict[str, list[int]] = defaultdict(list)
        self.degree: Counter[str] = Counter()
        self.in_degree: Counter[str] = Counter()
        self.out_degree: Counter[str] = Counter()
        self.edge_type_counts: Counter[str] = Counter()
        self.resolution_counts: Counter[str] = Counter()
        self.edge_types: list[str] = []
        self.resolutions: list[str] = []
        self.node_index_lower: list[tuple[str, str]] = []
        self._index(edges)

    def _index(self, edges: list[Any]) -> None:
        for e in edges:
            if not isinstance(e, dict):
                continue
            source = str(e.get("source", "")).strip()
            target = str(e.get("target", "")).strip()
            if not source or not target:
                continue
            edge_type = str(e.get("type", "UNKNOWN") or "UNKNOWN")
            resolution = str(e.get("resolution", "UNKNOWN") or "UNKNOWN")
            item = {
                "source": source,
                "target": target,
                "type": edge_type,
                "resolution": resolution,
                "dst_name": e.get("dst_name", ""),
                "dst_id": e.get("dst_id"),
            }
            idx = len(self.raw_edges)
            self.raw_edges.append(item)
            self.nodes.add(source)
            self.nodes.add(target)
            self.out_edges[source].append(idx)
            self.in_edges[target].append(idx)
            self.degree[source] += 1
            self.degree[target] += 1
            self.out_degree[source] += 1
            self.in_degree[target] += 1
            self.edge_type_counts[edge_type] += 1
            self.resolution_counts[resolution] += 1
        self.edge_types = sorted(self.edge_type_counts)
        self.resolutions = sorted(self.resolution_counts)
        self.node_index_lower = [(n.lower(), n) for n in sorted(self.nodes)]

    def meta(self) -> dict[str, Any]:
        return {
            "file": self.source_label,
            "node_count": len(self.nodes),
            "edge_count": len(self.raw_edges),
            "edge_types": self.edge_types,
            "resolutions": self.resolutions,
            "edge_type_counts": dict(self.edge_type_counts),
            "resolution_counts": dict(self.resolution_counts),
        }

    def search_nodes(self, q: str, limit: int) -> dict[str, Any]:
        q = q.lower().strip()
        if not q:
            return {"nodes": []}
        results = [node for low, node in self.node_index_lower if q in low]
        results.sort(key=lambda n: (-self.degree[n], n))
        return {
            "nodes": [
                {
                    "id": n,
                    "degree": self.degree[n],
                    "in_degree": self.in_degree[n],
                    "out_degree": self.out_degree[n],
                }
                for n in results[:limit]
            ]
        }

    def _edge_passes(self, idx: int, edge_type: str, resolution: str) -> bool:
        e = self.raw_edges[idx]
        return (not edge_type or e["type"] == edge_type) and (
            not resolution or e["resolution"] == resolution
        )

    def _resolve_focus(self, focus: str) -> str | None:
        focus = focus.strip()
        if not focus:
            return None
        if focus in self.nodes:
            return focus
        q = focus.lower()
        matches = [node for low, node in self.node_index_lower if q in low]
        if not matches:
            return None
        matches.sort(key=lambda n: (-self.degree[n], n))
        return matches[0]

    def _bfs_nodes(
        self, focus: str, depth: int, direction: str, edge_type: str, resolution: str
    ) -> set[str]:
        if depth <= 0:
            return {focus}
        seen = {focus}
        q = deque([(focus, 0)])
        while q:
            node, dist = q.popleft()
            if dist >= depth:
                continue
            edge_indices = []
            if direction in ("both", "out"):
                edge_indices.extend(self.out_edges.get(node, []))
            if direction in ("both", "in"):
                edge_indices.extend(self.in_edges.get(node, []))
            for idx in edge_indices:
                if not self._edge_passes(idx, edge_type, resolution):
                    continue
                e = self.raw_edges[idx]
                neighbors = []
                if direction == "out":
                    if e["source"] == node:
                        neighbors.append(e["target"])
                elif direction == "in":
                    if e["target"] == node:
                        neighbors.append(e["source"])
                else:
                    if e["source"] == node:
                        neighbors.append(e["target"])
                    if e["target"] == node:
                        neighbors.append(e["source"])
                for nb in neighbors:
                    if nb not in seen:
                        seen.add(nb)
                        q.append((nb, dist + 1))
        return seen

    def graph(
        self,
        edge_type: str = "",
        resolution: str = "",
        focus: str = "",
        depth: int = 1,
        direction: str = "both",
        min_degree: int = 0,
        max_degree: int = 0,
        limit: int = 500,
    ) -> dict[str, Any]:
        focus_resolved = self._resolve_focus(focus)
        if focus_resolved:
            candidate_nodes = self._bfs_nodes(
                focus_resolved, depth, direction, edge_type, resolution
            )
        else:
            candidate_nodes = set(self.nodes)
        candidate_nodes = {
            n
            for n in candidate_nodes
            if self.degree[n] >= min_degree
            and (max_degree <= 0 or self.degree[n] <= max_degree)
        }
        truncated = False
        if limit > 0 and len(candidate_nodes) > limit:
            truncated = True
            ordered = sorted(candidate_nodes, key=lambda n: (-self.degree[n], n))
            candidate_nodes = set(ordered[:limit])
        links = []
        visible_edge_types = set()
        visible_resolutions = set()
        for idx, e in enumerate(self.raw_edges):
            if not self._edge_passes(idx, edge_type, resolution):
                continue
            if e["source"] not in candidate_nodes or e["target"] not in candidate_nodes:
                continue
            links.append(e)
            visible_edge_types.add(e["type"])
            visible_resolutions.add(e["resolution"])
        linked_nodes = set()
        for e in links:
            linked_nodes.add(e["source"])
            linked_nodes.add(e["target"])
        if focus_resolved and depth == 0 and focus_resolved in candidate_nodes:
            linked_nodes.add(focus_resolved)
        nodes = sorted(linked_nodes, key=lambda n: (-self.degree[n], n))
        main_resolution = {}
        for n in nodes:
            c = Counter()
            for idx in self.out_edges.get(n, []):
                c[self.raw_edges[idx]["resolution"]] += 1
            for idx in self.in_edges.get(n, []):
                c[self.raw_edges[idx]["resolution"]] += 1
            main_resolution[n] = c.most_common(1)[0][0] if c else "UNKNOWN"
        return {
            "full_node_count": len(self.nodes),
            "full_edge_count": len(self.raw_edges),
            "focus_resolved": focus_resolved,
            "truncated": truncated,
            "edge_types": sorted(visible_edge_types),
            "resolutions": sorted(visible_resolutions),
            "nodes": [
                {
                    "id": n,
                    "degree": self.degree[n],
                    "in_degree": self.in_degree[n],
                    "out_degree": self.out_degree[n],
                    "main_resolution": main_resolution[n],
                }
                for n in nodes
            ],
            "links": links,
        }


def load_graph(path: Path) -> GraphStore:
    """Load a ``symbol_graph.json`` (top-level ``edges`` list, as ``build`` writes it)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"{path} is not valid JSON: {exc}") from exc
    edges = data.get("edges") if isinstance(data, dict) else None
    if not isinstance(edges, list):
        raise ValueError(f"{path} has no top-level 'edges' list.")
    return GraphStore(edges, source_label=str(path))


def int_param(params: dict[str, list[str]], name: str, default: int) -> int:
    try:
        return int(params.get(name, [str(default)])[0])
    except (TypeError, ValueError):
        return default


def str_param(params: dict[str, list[str]], name: str, default: str = "") -> str:
    return params.get(name, [default])[0]


def make_handler(store: GraphStore) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            sys.stderr.write("%s - %s\n" % (self.address_string(), format % args))

        def send_json(self, payload: dict[str, Any], status: int = 200) -> None:
            body = json.dumps(payload).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def send_html(self, body_text: str) -> None:
            body = body_text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self) -> None:
            parsed = urlparse(self.path)
            params = parse_qs(parsed.query)
            try:
                if parsed.path == "/":
                    self.send_html(HTML)
                    return
                if parsed.path == "/api/meta":
                    self.send_json(store.meta())
                    return
                if parsed.path == "/api/search_nodes":
                    self.send_json(
                        store.search_nodes(
                            str_param(params, "q", ""), int_param(params, "limit", 40)
                        )
                    )
                    return
                if parsed.path == "/api/graph":
                    self.send_json(
                        store.graph(
                            edge_type=str_param(params, "type", ""),
                            resolution=str_param(params, "resolution", ""),
                            focus=str_param(params, "focus", ""),
                            depth=int_param(params, "depth", 1),
                            direction=str_param(params, "direction", "both"),
                            min_degree=int_param(params, "min_degree", 0),
                            max_degree=int_param(params, "max_degree", 0),
                            limit=int_param(params, "limit", 500),
                        )
                    )
                    return
                self.send_json({"error": "not found"}, status=404)
            except Exception as exc:
                self.send_json({"error": str(exc)}, status=500)

    return Handler


def serve(graph_path: Path, host: str, port: int, open_browser: bool) -> int:
    """Serve the viewer until interrupted; return a process exit code."""
    path = graph_path.expanduser().resolve()
    if not path.is_file():
        print(
            f"Symbol graph not found: {path}\nRun `repo-wiki build` first.",
            file=sys.stderr,
        )
        return 1
    try:
        store = load_graph(path)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print(
        f"Loaded {len(store.nodes):,} nodes and {len(store.raw_edges):,} edges from {path}."
    )
    try:
        server = ThreadingHTTPServer((host, port), make_handler(store))
    except OSError as exc:
        print(f"Cannot bind {host}:{port}: {exc}", file=sys.stderr)
        return 1
    url = f"http://{host}:{server.server_address[1]}/"
    print(f"Serving viewer at {url} (Ctrl+C to stop)")
    if open_browser:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping.")
    finally:
        server.server_close()
    return 0

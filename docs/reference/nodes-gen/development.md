# Development

How to extend, test, and contribute to the package.

## Local setup

```bash
git clone git@github.com:the AKMS repository.git
cd AKMS
uv sync --project Packages/AKMS_nodes_gen
```

For docs work, also pull in the `docs` group:

```bash
uv sync --project Packages/AKMS_nodes_gen --group docs
```

## Running the docs locally

```bash
uv --project Packages/AKMS_nodes_gen run --group docs mkdocs serve -f Packages/AKMS_nodes_gen/mkdocs.yml
```

Opens at `http://127.0.0.1:8000/`. Live-reloads on save.

## Running the picker in dev mode

```bash
uv --project Packages/AKMS_nodes_gen run akms-pick --reload
```

`--reload` enables uvicorn's file watcher; saving any `.py` under the
package restarts the server. Static assets (`app.js`, `style.css`,
`index.html`) are reloaded by the browser; no server restart needed for
those.

## Code layout

| Module | Responsibility | Pure / has side effects |
|--------|----------------|--------------------------|
| `config.py` | Resolve paths from env | Pure |
| `plan_parser.py` | Markdown → list[Batch] | Pure (read only at the call site) |
| `loaders.py` | BBT JSON + ZotSums → Catalog | Pure (reads fs) |
| `state.py` | batch_assignments.json IO | I/O |
| `queries.py` | saved_queries.json IO | I/O |
| `exporters.py` | plan JSON, PDF stage, nlm shell | I/O + subprocess |
| `server.py` | FastAPI app, FilterSpec, _Repo | I/O via the above |
| `__main__.py` | argparse + uvicorn | I/O |
| `nlm_batch.py` | serial NLM node generation, cache, local gates | I/O + subprocess |
| `static/*` | Browser UI | (no Python) |

The four pure modules (`plan_parser`, `loaders`, `state` (read), `queries`
(read)) are the natural unit-test surface. The exporters and server can be
exercised through `fastapi.testclient.TestClient` against a fixture
catalog.

## Testing patterns

There is no `tests/` folder yet — adding one would be an easy win. The
shape that fits this codebase:

```
Packages/AKMS_nodes_gen/tests/
└── batch_picker/
    ├── conftest.py          # shared fixtures (Paths, fake catalog)
    ├── test_plan_parser.py  # parse_plan against known plans + edge cases
    ├── test_loaders.py      # BBT itemID → citekey join, ZotSums frontmatter parsing
    ├── test_state.py        # round-trip serialization + dedup
    ├── test_server.py       # TestClient over /api endpoints
    └── fixtures/
        ├── plan_minimal.md
        ├── zsumbib_minimal.json
        └── zotsums_papers/
            └── @paper_a.md
```

Suggested first tests:

```python
def test_parse_plan_recognizes_node_count_mismatch(tmp_path):
    plan = tmp_path / "plan.md"
    plan.write_text(
        "# Round 1: Test\n"
        "## R1_B1 — Mini (3 nodes)\n"
        "**PDF folder:** `AKMS_Sources/new/R1_B1_mini/`\n"
        "**Sources:** A, B\n\n"
        "| # | Node ID | Title | Size |\n|---|---|---|---|\n"
        "| 1 | `n-one` | One | small |\n"
        "| 2 | `n-two` | Two | small |\n"
    )
    [b] = parse_plan(plan)
    assert b.node_count == 3
    assert len(b.nodes) == 2  # parser surfaces the mismatch
    assert b.pdf_slug == "R1_B1_mini"


def test_filter_spec_round_trips_through_saved_query(client):
    spec = {"q": "phase field", "only_with_pdf": True, "suggest_for": "R7_B2"}
    r = client.put("/api/saved_queries/test", json={"filter": spec})
    assert r.status_code == 200
    r = client.get("/api/saved_queries")
    [saved] = [q for q in r.json() if q["name"] == "test"]
    assert saved["filter"] == {**spec,
        "collection": [], "year_from": None, "year_to": None, "item_type": ""
    }
```

## Coding conventions

- **Type hints everywhere.** The package uses `from __future__ import annotations` and PEP 604 (`X | None`).
- **Dataclasses for data, Pydantic only for HTTP boundaries.** Internal data uses `@dataclass`; request/response bodies use `BaseModel`.
- **Atomic writes.** Anything writing JSON to disk uses `tempfile.mkstemp` + `os.replace` (see `state.save_state`, `queries.save_queries`).
- **No comments unless WHY-only.** Identifier names + tight functions carry the WHAT. Comments call out non-obvious invariants (e.g. "items are integer itemIDs, not itemKeys").
- **No docstrings on `__init__` / `to_dict`.** Frontmatter-style docstrings only on modules and the public functions inside them.
- **Vanilla JS in the UI.** No bundler, no framework. The `static/app.js` is one ~700-line file by design.

## Adding a new endpoint

1. Add a request model to `server.py`'s Pydantic block if you need a body.
2. Add the route inside `create_app`.
3. If it mutates batch state, call `repo.save_state()` before returning.
4. If it mutates queries, call `repo.save_queries()`.
5. Update `docs/batch-picker/api-reference.md` with the new shape.
6. Wire it from `static/app.js` — typically a `fetch` helper plus a UI handler.

## Adding a new filter dimension

1. Add the field to `FilterSpec` (Pydantic model in `server.py`).
2. Wire it through `_filter_papers` (one new branch in the per-paper loop).
3. Add the matching query parameter to `/api/papers`.
4. Add the UI control to `static/index.html` and the read in
   `app.js:currentFilter()`.
5. Make sure `applyFilterToToolbar()` knows how to set the new control
   from a saved query.

## Adding a new pipeline action button

1. Implement the side-effecting helper in `exporters.py`. Return an
   `ActionResult(ok, message, data)`.
2. Add a `POST /api/batches/{batch_id}/<action>` route in `server.py`.
3. Persist any state changes before returning.
4. Add the button + handler in `static/index.html` + `app.js`.
5. Document the new endpoint in `api-reference.md` and the button in
   `ui-tour.md`.

## Working on the UI

The CSS uses a small set of CSS variables defined in `:root`. Keep new
styles consistent — don't introduce a third tone of orange.

The JS state lives in a single `state` object near the top of `app.js`.
When in doubt about whether to add a new field, do — there's no
performance budget at this scale.

Avoid introducing a build step. Keeping the UI as a single static folder
is a feature: anyone can read every line, and there's nothing to install
to iterate on it.

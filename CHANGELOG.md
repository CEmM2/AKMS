# Changelog

All notable changes to the public AKMS packages are documented here. The
public history begins with the first curated release; earlier private
development is intentionally not replayed.

## [Unreleased]

### Security
- The lockfile moves past 15 advisories published after 0.3.2: aiohttp
  3.14.5 (eight, including request smuggling in the pure-Python parser),
  certifi 2026.10.23 (emSign roots with compromised intermediates), filelock
  4.2.4 (three `ReadWriteLock`/`SoftFileLock` issues), mcp 1.30.0 (unbounded
  StreamableHTTP sessions) and the OpenTelemetry 1.45.1 family (unbounded
  `tracestate` parsing). All are within the declared ranges, so this is a
  lock-only change; `uv audit` reports no known vulnerabilities.

### Added
- `repo-wiki` answers code-intelligence questions from its symbol graph, with
  no server and no model: `repo-wiki context SYMBOL` shows a symbol's
  definition, callers, callees and module imports; `repo-wiki impact SYMBOL`
  lists its dependents grouped by depth (d=1 will break, d=2 likely affected,
  d=3 may need testing) with a LOW/MEDIUM/HIGH/CRITICAL risk; and
  `repo-wiki changes [--base REF | --staged | --worktree]` maps a git diff,
  including renames, deletions and untracked files, to the symbols it touches
  and their direct callers, flagging callers of deleted symbols. Python calls
  are resolved through scopes, imports, `self` and base classes; links that rest
  only on a name match are reported separately as possible and never raise the
  risk. All three take `--json`, refuse a stale graph unless `--allow-stale` is
  given, and exit 3 for a graph problem and 4 for an unknown or ambiguous
  symbol.
- A bundled `repo-wiki-code-intel` agent skill teaches when to run each
  command: `context` when exploring, `impact` before editing a function, class
  or method, and `changes` before committing.
- `failure-memory hooks install|uninstall|status` installs `post-checkout`,
  `post-commit`, `post-merge` and `post-rewrite` git hooks, so a checkout or
  a plain `git commit` no longer leaves generated lessons or code mirrors
  missing or stale. The hooks go where git
  runs them (`git rev-parse --git-path hooks`, so `core.hooksPath` and linked
  worktrees are respected). A missing hook is created owner-only (`0700`;
  widen it yourself where other users' commits must run it); an existing
  shell hook keeps its mode and gets a marked block after its `#!` line and
  is otherwise kept byte for byte;
  hooks in other languages, symlinked, non-executable or tracked hooks are
  refused, not edited. Install is idempotent and uninstall removes only the
  block. The global vault, project root and config path are kept in git
  config under `akms-failure-memory.*`. The hooks call `failure-memory hooks
  run`, which skips file checkouts and the steps of a rebase (refreshing once
  at its end), refreshes a multi-commit cherry-pick or revert once after its
  last commit and an amend once, honours `AKMS_FAILURE_MEMORY_HOOKS=0`, skips
  with a warning when the project lock is busy, and always exits 0. Running
  install again over an install without `post-commit` adds it.
- `failure-memory refresh if-stale [--since <ref>]` refreshes only what is
  stale: lessons recompile when `check` reports drift, mirrors are exported
  through the exporter's git selection for the sources that changed since
  `--since` or the last recorded `if-stale` run (a full export, with the
  reason in the result, when there is no usable base), and the graph is
  rebuilt when either changed. It always stamps the current UTC time and
  never rewrites outputs marked `committed`. Projects that do not use it or
  the hooks see no change.
- `akms-failure-memory` can allocate collision-free lesson IDs:
  `validation.id_style = "dated"` gives `L<YYYYMMDD>-<4 Crockford base32>`
  IDs, so lessons added on two branches no longer collide. `"sequential"`
  stays the default, and existing `L001`-style IDs keep working alongside the
  new form.
- Opt-in registry schema 2 (`validation.registry_schema_version = 2`): the
  registry is a directory of one `<ID>.json` file per lesson plus
  `_registry.json`, so adding lessons on two branches no longer conflicts.
  Schema 1 stays a single JSON file and is still what `failure-memory init`
  writes.
- `failure-memory registry migrate --to 2 [--check]` splits a schema 1 file
  into that directory; `--check` compiles both forms without changing the
  repository. A consumer-contract v2 pack covers the directory form.
- `akms-failure-memory` toolchain pins accept version ranges:
  `toolchain.akms_version` and `toolchain.repo2md_version` take a plain
  version, still matched exactly, or a PEP 440 specifier set such as
  `">=0.3.2,<0.4"`, matched as a range. A project that pinned a range got a
  permanent `akms_version_drift` advisory, because a range never equals a
  version. A value containing any of `<`, `>`, `=`, `!`, `~` or `,` is a
  specifier set; a value that is neither a valid version nor a valid
  specifier set fails config loading with `invalid_config`. Pins are kept as
  written, so existing config fingerprints do not change. `packaging` is now a
  declared dependency (`>=24,<27`).
- `akms` now ships the repository wiki and code-mirror exporter that was
  previously installed separately as `repo-wiki`, with the same subcommands
  and flags (`init`, `scan`, `parse`, `build`, `index`, `query`, `summarize`,
  `export-akms`, `stats`, `graph`, `clean`). Run it as `repo-wiki`,
  `akms wiki` or `python -m akms.repo_wiki`. Python needs nothing beyond
  `akms`, and C++ works through an installed `doxygen`. `akms[rust]`,
  `akms[cpp]` and `akms[julia]` add the tree-sitter grammars, and
  `akms[multilang]` adds all three. `akms[all]`
  now includes `multilang`. Repositories keep their `.repo_wiki/` directory
  and configuration. The scanner no longer follows symbolic links. A link
  that points outside the repository used to abort the scan. It is now
  listed as skipped, with the reason `symlink`, or `excluded` when an
  ignore or exclude pattern matches it.
- A `builtin` code-mirror provider runs that exporter
  (`python -m akms.repo_wiki export-akms`) in a subprocess, with the same
  export contract, validation, timeout and lock as `repo2md`, and needs
  nothing else installed. It writes mirrors into the knowledge directory the
  graph reads, so a repository on `.knowledge/` now loads its mirror; an
  external `repo-wiki` still always writes `knowledge/code-mirror/`.
- `repo-wiki export-akms` gains `--knowledge-dir .knowledge|knowledge`, the
  directory under `--output` that receives `code-mirror/`. It defaults to
  `.knowledge`; pass `knowledge` for the older layout. The committed export
  fixture pack keeps its `knowledge/` paths and its digest.
- `akms migrate-layout` moves an existing `<repo>/knowledge/` to
  `<repo>/.knowledge/`: with `git mv` when tracked, re-anchoring
  `.gitignore` and `.gitattributes` lines on it, dropping the compiled graph
  and qmd cache, and listing other tracked lines that still mention
  `knowledge/`. `--check` changes nothing; a failure part-way restores the
  directory and the edited files. `failure-memory migrate-layout` does the
  same for the directory under `akms_repo_root` and also moves the
  configured paths, `generated_warning` and a configuration stored inside
  the directory, then recompiles lessons when given `--global-vault`. The
  configuration fingerprint changes once. `akms status` warns when
  `.knowledge/` hides a non-empty `knowledge/`.
- `akms-failure-memory` chooses its mirror exporter with
  `[toolchain].mirror_provider`. `"builtin"` uses the exporter shipped in
  akms and needs none of the `repo2md_*` keys, and preflight no longer looks
  for an external `repo-wiki` or its checkout. `"repo2md"` keeps the external
  tool and still requires those keys; it is what a configuration without the
  key uses, so existing projects and the frozen consumer-contract packs are
  unchanged. `failure-memory init` now writes `mirror_provider = "builtin"`
  without the `repo2md_*` keys. Preflight results gain a `mirror` object
  naming the provider; the `repo2md` object is reported only for that
  provider.
- `akms status` lists code mirrors older than their source under "Stale
  Code Mirrors". A mirror is stale when its source file was committed after
  the mirror's `generated_at`, was edited after it and not yet committed, or
  no longer exists. The check reads the mirror files and git history, so it
  needs no change to the frozen mirror schema. Refreshing the mirror clears
  the entry. When the repository has code mirrors the section always
  appears: `Stale Code Mirrors: 0` with the number checked when all are
  current, and `Stale Code Mirrors: not checked` with the reason outside a
  git repository or when git fails, so a clean run is told apart from a
  skipped one. The JSON report carries the same facts under
  `mirror_freshness` (`mirrors`, `checked`, `skipped`) beside the
  `stale_mirrors` list.
- `akms-failure-memory` can index lessons as cards. With
  `[compatibility].lesson_index_version = "failure-lesson-index/v1"`,
  `compile` writes `lesson_index.json` and `lesson_index.md` beside the route
  index: lessons grouped by area, package and module, each as a card with
  its ID, title, trigger, mechanism, prevention, reference IDs and reviewed
  categories. The index has no timestamps and is byte-identical across
  rebuilds. Generated node titles then come from the record (the first
  clause of `root_cause`, else `symptom`) instead of the line hint; node IDs
  and routes are unchanged. Node bodies open with a `## Summary` holding the
  first sentence of `root_cause` and of `prevention`, which AKMS loads for
  coactivated lessons instead of the full body. Those sentences are not
  repeated below: `### Root cause` and `### Prevention` keep only the rest,
  and are omitted when nothing is left. The `## Identity` block is dropped.
  `failure-memory init` writes the key. A configuration without it keeps
  line-hint titles and the original body and writes no index, so existing
  projects, their config fingerprints and the frozen consumer-contract packs
  are unchanged.
- `failure-memory index` browses the index read-only: with no selector it
  lists the groups, `--area`, `--package`, `--module` and `--grep` return
  cards, and `--expand <ID>` returns the full registry record. It rebuilds
  the index from the registry, so it is current before the next `compile`,
  and reports whether the published index is `current`, `stale`, `absent`
  or `disabled`.
- A versioned annotations sidecar (`failure-lesson-annotations/v1`) holds
  reviewed failure-mechanism categories, contradictions, exceptions,
  supersession and applicability without changing the lesson schema:
  `lessons.annotations.json` next to a schema 1 file, `_annotations.json`
  inside a schema 2 directory. It is validated on every compile; an unknown
  lesson ID fails with `annotation_id`. It does not change generated nodes,
  routes or the registry digest. `registry migrate --to 2` copies it into the
  new directory.

### Changed
- Loadouts render coactivated (`load_with`) nodes as their `## Summary`
  instead of in full, by default: new setting
  `loadout.coactivated_reading_priority` (default `summary`; `full` restores
  the earlier behaviour). A node without a `## Summary` section is still
  rendered in full. On a real failure-memory project baseline this removes
  about 74% of coactivated tokens once lessons carry summaries.
- Exact task resolution follows `load_with` from required nodes only; new
  setting `loadout.coactivate_from_advisory` (default `false`) restores
  advisory sources.
- The default code-mirror provider (`mirror.provider`) is now `builtin`
  instead of `legacy`. `akms generate-mirror`, the staged runner and the
  `akms_generate_mirror` MCP tool use it unless a project configures
  another provider. Its mirrors cover every language the exporter supports,
  not only Python, and their Markdown layout differs from `legacy`'s; both
  are valid v2 code-mirror nodes. With the default `changed` selection it
  exports sources changed since the parent branch (`git diff <parent>`, so
  uncommitted changes to tracked files count). In a directory that is not a
  git repository, or that lacks the parent branch, it selects nothing and
  logs a warning, as `legacy` did; `generate-mirror` prints the warning on
  stderr, the staged runner records it, and with `mirror.require_success`
  it is a `selection_unavailable` failure. New files git does not ignore
  are selected too, and mirrors of sources deleted or renamed away are
  removed. An explicit `--path` naming a deleted source removes its mirror;
  one naming no source and no mirror is an error, where `legacy` skipped
  it. Set `mirror.provider: legacy` to keep the old behaviour.
- `repo-wiki export-akms` and the `builtin` mirror provider now skip a source
  that does not parse (for example a Python file with a syntax error
  mid-edit) and export the rest. Before, one such file failed the whole
  export: nothing was written, `repo-wiki` exited 1, and the staged runner
  blocked the post-phase graph rebuild. The skipped source appears in the
  export JSON under `skipped` with reason `parse_error`, keeps its existing
  mirror, and is not pruned; `akms generate-mirror` warns on stderr and the
  staged runner records a warning. Render, decode, selection and write
  errors still fail the export. `repo-wiki export-akms --strict-parse` and
  the `mirror.strict_parse: true` option restore the old all-or-nothing
  behaviour for the `builtin` provider. The external `repo2md` provider is
  unaffected.
- `akms-failure-memory` provider fingerprints no longer include the installed
  `akms` release version. The packages release in lockstep, so every patch
  release moved every fingerprint, marking existing resolutions stale and
  breaking the frozen consumer-contract pack, whether or not resolution
  changed. Schema and provider-contract changes still move fingerprints
  (`akms_schema_version`, `PROVIDER_VERSION`), as does the AKMS version a
  project pins in its own `[toolchain]` table. Existing fingerprints change
  once on upgrade.
- The consumer-contract pack (`tests/fixtures/consumer_contract/v1`) is
  re-frozen with the new fingerprints; its pack digest is now
  `bd1c2dc3a1d35ab41d7203aecce1bd1d39a494dde1532c9360b9e3518f2f8735`.
  Consumers that pin the pack must update that digest; behaviours, requests
  and lessons are unchanged.

- `failure-memory init` pins `akms_version` to the installed AKMS minor
  series, `">=<installed>,<<major>.<minor + 1>"` (for example
  `">=0.3.2,<0.4"`), instead of a hard-coded `"0.6.1"` that made every new
  project report version drift on its first refresh.
- New projects keep their knowledge in `<repo>/.knowledge/`: lessons, the
  compiled graph and generated outputs. An existing `knowledge/` directory is
  still used when `.knowledge/` is absent, and `build_graph`'s signature is
  unchanged. The bundled qmd scripts and the skill's `akms_bootstrap.sh`
  follow the same rule. When run from the akms package, the qmd scripts now
  search the repository they are run from; before, they looked inside the
  installed package and found no local nodes, mirror or sessions.
- The documentation, the bundled skills, the CLAUDE.md kernel and
  `examples/sample-project` now use the `.knowledge/` layout. The frozen v2
  specification still names `knowledge/`.
- A registry schema 2 source digest is SHA-256 over the registry files sorted
  by filename (name, NUL, raw bytes, NUL each, `_registry.json` included).
  Schema 1 digests are unchanged. Migrating a registry changes its lesson
  fingerprints once.
### Fixed
- `akms status` no longer lists nodes reached through `load_with` as
  orphans. A node that names others in `load_with`, or that another node
  names there, is reached by coactivation even without edges; a
  failure-memory project's lessons with related lessons all appeared under
  **Orphaned Nodes**. Nodes with no edges and no `load_with` link are still
  listed.
- `akms status` no longer lists route targets as orphans either. It finds the
  task route index the way reviewer required-knowledge does, or uses the ones
  given with the new `--routes PATH` option (repeatable), and a node that a
  `by_path` or `by_symbol` route names is not an orphan. The section heading
  now reads "no edges, load_with or route" and names the route index used. A
  route index that cannot be read or parsed is reported under **Route Index
  Warnings** instead of failing the report. The report adds `route_index`,
  `route_indexes` and `route_index_warnings`; existing keys are unchanged.
  [Addendum 0001](docs/specification/addenda/0001-health-reporting-reachability.md)
  to §5.7 states the rule and [ADR 0003](docs/adr/0003-reachability-in-health-reporting.md)
  records why. No schema field changes.
- Reviewer required-knowledge did not find the route index written by
  `akms-failure-memory` at its default path,
  `.knowledge/generated/failure_routes.json`, and fell back to tag-based
  loadouts. `generated/failure_routes.json` under `.knowledge/` and
  `knowledge/` is now searched after every earlier location, so repositories
  that resolved to a route index before still resolve to the same one. The
  search lives in `akms.task_context.routes.find_task_route_index`, shared by
  the reviewer and `akms status`.
- Loadouts: a node with `reading_priority: summary` and no `## Summary`
  section is now rendered in full, as FR-L10c specifies. It used to get its
  first five non-heading lines as a "summary", which for generated nodes is
  the generated-file banner and identity bullets. Routing-mode nodes without
  a `reading_priority` are unchanged.
- `failure-memory` preflight read the external repo2md integration pin from
  `dev/plans/mirror_export/release/`, but repo2md keeps it under
  `dev/plans/akms_mirror_export/release/`. The fixture identity check could
  never pass against a real checkout and always reported
  `repo2md_fixture_unreadable`.
- `akms-failure-memory`'s project lock no longer sends console Ctrl-C events
  on Windows. Its owner-liveness probe used `os.kill(pid, 0)`, and on Windows
  signal 0 is `CTRL_C_EVENT`: every 20 ms of lock contention interrupted every
  process on the console, and a dead owner was never detected, so stale-lock
  recovery never worked there. Windows now probes with
  `OpenProcess`/`GetExitCodeProcess`; POSIX is unchanged. A new Windows CI job
  runs the probe tests.
- The published consumer-contract pack failed its own `verify_pack.py`: its
  lessons, generated nodes and recording files had been edited without
  updating their digests, and the conformance suite that checks it skipped
  under every released `akms` version. The suite now runs on every release,
  and `tests/refreeze_consumer_pack.py` regenerates the pack when a deliberate
  contract change needs it.
- The `akms-learn` wheel and sdist shipped none of the exporters' Jinja
  templates (`templates/*.md.j2`, `exporters/templates/*.html.j2`), so every
  markdown or HTML export from a pip install raised `TemplateNotFound`. The
  package now declares them as package data, and a smoke test that CI runs
  against the built wheels fails if they go missing again.

## [0.3.2] — 2026-10-06

### Added
- Every package declares its homepage, documentation, source, issue tracker
  and changelog, so its PyPI page links back to the project.
  `scripts/check_versions.py` fails if a package loses them.
- `akms --version` prints `akms <version>` from the installed distribution's
  metadata and exits 0. Host adapters probe it before `--help`; without it they
  could only report an unknown version and skip strict compatibility checks.
- `akms[learn]`, `akms[failure-memory]`, `akms[nodes-gen]`, `akms[compmech]`
  and `akms[all]` install the companion packages through `akms`, pinned to the
  same minor series. `scripts/check_versions.py` fails the release if those
  pins drift from the `akms` version.

### Fixed
- `akms deprecate`, `akms suppress` and `akms promote` now delete the compiled
  `knowledge/graph/graph.json` and the qmd cache. Before, `resolve-task`,
  `query` and `loadout` kept reading the old graph, so a deprecated node was
  still resolved as required until someone deleted the file by hand. The next
  reader now recompiles, and a required node that is no longer loadable fails
  with `required_node_unavailable`.
- `graph_version` no longer changes when the graph is recompiled from
  identical inputs. It hashed the whole `graph.json`, including its
  `generated_at` timestamp, so every rebuild produced a new graph version and
  a new resolution fingerprint. It now hashes the graph's canonical JSON
  without that timestamp. Existing graph versions and fingerprints change once
  on upgrade.
- `akms.__version__` and `akms_failure_memory.__version__` had stayed at 0.3.0
  through the 0.3.1 release, so `failure-memory --version` and the akms
  toolchain fingerprint reported the wrong version. Both literals now match
  `pyproject.toml`, and `scripts/check_versions.py` fails the release when they
  drift again.
- `akms-mcp-stdio` is now installed as a command. It was registered in a
  custom entry-point group, so the command the MCP docs tell you to run did not
  exist. Without the `mcp` extra it now exits with an install hint.
- `compmech-reference-pack` declares its Apache-2.0 licence and ships the
  licence file, and its Python range now matches its dependencies (3.12).
- Every dependency one package in the family has on another is bounded to the
  current minor series (`akms-learn` on `akms`, `compmech-reference-pack` on
  `akms-learn`, the MechDSL backend to 0.2). `scripts/check_versions.py` now
  rejects an unbounded or stale sibling requirement.
- `failure-memory` commands default `--config` to the file `init` writes, so
  `failure-memory doctor --repo .` works straight after `init`.

- `akms-pick` crashed on start-up in every 0.3.1 install: one route's return
  annotation is rejected by the FastAPI version the package requires, and no
  test built the app. A smoke test now starts the installed command.

### Changed
- `akms-pick` no longer needs an AKMS checkout. `--plan`, `--bibtex-json`,
  `--zsum-root` and `--workspace` locate its inputs from anywhere, falling back
  to the existing environment variables. Its own files default to the plan's
  directory rather than `Sources_Evals/NLM/`; `AKMS_REPO_ROOT` restores the
  old layout. The plan's `PDF folder` field accepts any path.
- `akms-pick` starts with a missing plan, Zotero export or zsum vault and
  lists what is missing in the terminal and in a banner on the page. Without
  zsum it points to [zsum](https://github.com/CEmM2/zotero-summarizer) as the
  simpler route rather than failing.
- CI installs every `akms[...]` extra and pairing from the freshly built wheels
  and checks each installs exactly its companions and their commands.
- The public-tree audit now also fails on private project names and internal
  plan or decision references in the published tree.

### Security
- `akms[orchestration]` and `akms-nodes-gen[llm]` require `litellm>=1.96.2`
  (was 1.84.0), which excludes every release affected by GHSA-3cv6-jpf6-8222
  (authenticated SSRF and provider-credential exfiltration). Newer litellm
  also pulls in `boto3`. The lockfile moves `pyjwt` to 2.15.1, `urllib3` to
  2.8.0 and `multidict` to 6.9.1 (GHSA-54p9-h82j-f925, a reference leak in
  its items-view operations); `uv audit` reports no known vulnerabilities.

## [0.3.1] — 2026-09-10

### Added
- `compmech-reference-pack`, the computational-mechanics companion adapter,
  joins the published set. It bridges `akms-learn` LSP excerpts to the
  [MechDSL](https://github.com/CEmM2/MechDSL) executable backend; the compile
  path is an optional `mechdsl` extra, so the backend is not pulled into a
  consumer's resolution unless asked for. It could not ship in 0.3.0 because
  its only hard dependency, `akms-learn`, was not yet on PyPI.
- `akms vault status` and `akms vault install`. With no argument, `install`
  fetches the canonical
  [compmech vault](https://github.com/CEmM2/akms-vault-compmech), pinned to a
  release tag. It also accepts a directory, a `.tar.gz`, or an https URL, and
  refuses to replace a populated vault without `--force`.

### Changed
- The node corpus no longer ships inside the `akms` wheel, which drops it from
  1.3 MB to 320 KB. The corpus was never reachable from the package —
  `resolve_global_vault` has four precedence levels and the package directory
  is on none of them — so nothing could read it. Vaults are distributed and
  installed separately now; see `akms vault install`.
- `package-data` is enumerated rather than globbed, so a corpus placed back
  under `_bundled` cannot silently re-enter the wheel.

### Fixed
- Documentation referenced `Packages/AKMS` and similar paths 37 times across
  14 files. The tree ships `packages/akms`; those commands resolved only on a
  case-insensitive filesystem and failed on Linux.
- The installation guide stated that no PyPI release existed, and warned that
  a full workspace sync required a sibling checkout that is not part of the
  public tree.
- Material icons on the documentation site rendered as literal text
  (`:material-graph:`) because `pymdownx.emoji` was not enabled, and the
  companion-adapter card had lost its title line.
- `site_url`, `repo_url` and `edit_uri` were unset, so canonical links and the
  sitemap pointed nowhere.

### Notes
- All five packages release in lockstep, so the four unchanged since 0.3.0 are
  republished at 0.3.1 with no content change.

## [0.3.0] — 2026-08-31

### Added
- First public research preview: `akms` (deterministic knowledge compiler,
  projections, evidence ingestion, CLI, optional embedded runtime),
  `akms-learn` (learning-packet compiler, experimental preview),
  `akms-nodes-gen` (node generation and validation tooling), and
  `akms-failure-memory` (deterministic project-owned failure memory).

### Notes
- All packages release in lockstep. The initial public version is 0.3.0,
  continuing `akms-failure-memory`'s prior 0.1.0–0.3.0 release line so that
  already-distributed wheels upgrade cleanly.

# Changelog

All notable changes to the public AKMS packages are documented here. The
public history begins with the first curated release; earlier private
development is intentionally not replayed.

## [Unreleased]

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

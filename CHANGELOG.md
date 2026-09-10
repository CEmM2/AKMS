# Changelog

All notable changes to the public AKMS packages are documented here. The
public history begins with the first curated release; earlier private
development is intentionally not replayed.

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

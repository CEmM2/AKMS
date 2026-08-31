# Changelog

All notable changes to the public AKMS packages are documented here. The
public history begins with the first curated release; earlier private
development is intentionally not replayed.

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

# Changelog

## 2026-05-10

### Added

- Added `akms_nodes_gen.nlm_batch`, a serial NotebookLM batch generator that
  runs one selected batch/cluster against that batch's notebook.
- Added CLI parameters for source IDs, timeout, output format, NotebookLM
  prompt file, and output template file so generation policy stays outside the
  Python implementation.
- Added local mitigation gates for NLM-only generation: response caching,
  raw-response audit files, resumable state, fenced YAML/JSON parsing, schema
  checks, known-edge validation, required source references, and repair retries.
- Added focused unit tests for batch loading, structured response parsing,
  grounding/edge validation, and serial run behavior.

### Documentation

- Added the `nlm_batch.py` tool guide.
- Populated the package README with install, picker, generator, and docs usage.
- Linked the new generator from the docs home, tools index, API reference, and
  MkDocs navigation.

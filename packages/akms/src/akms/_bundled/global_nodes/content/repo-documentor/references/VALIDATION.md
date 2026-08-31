# Validation & verification documentation

## Required outputs
- `docs/validation/verification-map.md`
- `docs/validation/tests-to-modules.md`
- `docs/validation/benchmarks.md` (if performance-relevant)

## Verification map contents
- Unit tests: what modules/functions they cover
- Numerical regression tests:
  - golden outputs
  - tolerances
  - fixed seeds/configs
- Benchmarks:
  - inputs
  - hardware assumptions
  - expected runtime/memory ranges
- Datasets/fixtures:
  - provenance
  - versioning
  - checksums/hashes (when available)
- “Sanity expectations”:
  - example plots/images and what “correct” looks like (described, not necessarily embedded)

## SymPy or analytic verification (optional but recommended)
Where tensor ops or derived formulas exist:
- include a short analytic check plan
- list identities and what is verified
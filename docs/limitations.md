# Known limitations

AKMS is research software published as a preview. This page lists the limits
we know about; absence from this list is not a guarantee.

## Capability maturity

| Surface | Status |
|---|---|
| Core graph compilation, deterministic queries, projections, evidence ingestion | Stable |
| `akms` CLI | Stable |
| Read-only global vault + writable project overlay model | Stable |
| Embedded first-party runtime (`akms.orchestrator`, `akms.agents`) | Experimental — optional, install via `akms[orchestration]` |
| MCP tool server | Experimental — install via `akms[mcp]` |
| `akms-learn` (learning-packet compiler) | **Experimental preview** |
| `akms-nodes-gen` (node generation, batch picker) | Experimental — requires external tools for generation |
| `akms-failure-memory` | Beta |
| OpenTelemetry export | Experimental — install via `akms[telemetry]` |

## Performance

- **Dense cyclic subgraphs compile slowly in `akms-learn`.** Deterministic
  ordering breaks cycles by re-running a topological sort per removed edge,
  which is roughly quadratic in the number of cycles. A dense ~50-node cluster
  (e.g. an FFT-Galerkin + spectral slice) can take minutes, while comparable
  sparse slices finish in ~2 s. The output is correct, just slow. Reproduce:

  ```bash
  # ~2 s:
  akms-learn compile --graph graph.json --topic "Finite-Strain Kinematics" \
    --seed-tags finite-strain --seed-tags kinematics --max-nodes 12 \
    --generation-option default --export markdown
  # minutes on a dense cyclic cluster:
  akms-learn compile --graph graph.json --topic "FFT-Galerkin Micromechanics" \
    --seed-tags fft-galerkin --seed-tags spectral --max-nodes 12 \
    --generation-option default --export markdown
  ```

- `--max-nodes` caps the reading order, but seed expansion may pull a larger
  cluster before the cap applies, inflating ordering work.

## External tool and provider requirements

- **qmd** (Go binary) powers some search paths; without it those paths fall
  back to `grep` with reduced ranking quality.
- **nlm** (NotebookLM CLI) is required for grounded node generation; without
  it, generation paths that need it report the tool as unavailable.
- The embedded runtime's agent backends need either provider SDKs
  (`akms[agents]`) or the `claude` / `codex` binaries on PATH, depending on
  the selected backend.
- LLM expansion in `akms-learn` requires an explicitly configured provider;
  with none configured it uses a deterministic built-in stub (clearly labeled
  in the output provenance).

## Scope

- AKMS does not own portfolio-wide orchestration. The embedded runtime is a
  bounded, optional workflow; broader coordination belongs to external
  consumers of the projection and evidence contracts.
- The bundled corpus (302 nodes) is heavily domain-skewed: computational
  solid mechanics, plus a large block describing the MOOSE framework. It
  demonstrates the system on one domain; it is not a general knowledge base.
- Corpus nodes differ in provenance and confidence. 52 are author-written,
  180 are author-reviewed summaries of published literature, and 70 are
  machine-generated summaries of a third-party codebase; 88 of the 302 carry
  `status: tentative`. Each node's `source` and `status` fields record this —
  consult them before relying on a node. See `THIRD_PARTY_NOTICES.md`.
- Python 3.12 only in this release.

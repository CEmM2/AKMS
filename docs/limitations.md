# Known limitations

AKMS is research software published as a preview. This page lists the limits
we know about; absence from this list is not a guarantee.

## Capability maturity

Maturity and installation footprint are separate axes. "Optional" means the
surface is not installed by a bare `pip install akms` and needs an extra or an
external tool; it says nothing about how well-tested the surface is.

| Surface | Maturity | Installation |
|---|---|---|
| Core graph compilation, deterministic queries, projections, evidence ingestion | Stable | base package |
| `akms` CLI | Stable | base package |
| Read-only global vault + writable project overlay model | Stable | base package |
| MCP tool server (`akms-mcp-stdio`, same operations as the CLI) | Stable | optional, `akms[mcp]` |
| OpenTelemetry export | Stable | optional, `akms[telemetry]`; inert without an exporter |
| `akms-nodes-gen` (batch picker, converters, validators) | Stable | separate package; grounded generation needs the external `nlm` CLI, ranked search needs `qmd` |
| `akms-failure-memory` | Beta | separate package |
| Embedded first-party runtime (`akms.orchestrator`, `akms.agents`) | Experimental | optional, `akms[orchestration]`; needs provider SDKs or the `claude` / `codex` binaries |
| `akms-learn` (learning-packet compiler) | **Experimental preview** | separate package |

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
- No knowledge corpus ships inside the packages. `akms vault install` fetches
  the [compmech vault](https://github.com/CEmM2/akms-vault-compmech), which
  covers one domain (computational solid mechanics, plus the MOOSE framework)
  and is not a general knowledge base. Its README's *Provenance* section and
  each node's `source` and `status` fields say how a node was produced;
  consult them before relying on one.
- Python 3.12 only in this release.
- Linux and macOS only. CI tests both; Windows is not tested and not
  supported in this release. The agent skills, git hooks and qmd helper
  scripts AKMS ships are bash, and parts of the CLI write characters the
  default Windows console encoding cannot represent. The pure-Python core may
  well work under WSL, but nothing here verifies that.

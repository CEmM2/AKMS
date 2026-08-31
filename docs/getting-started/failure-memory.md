# Getting started

## 1. Initialize

```bash
failure-memory init \
  --repo . \
  --config .failure-memory/config.toml \
  --repository-id example \
  --node-namespace example-failure

failure-memory doctor --repo . --config .failure-memory/config.toml
```

Review the generated configuration. Paths are repository-relative and checked
for containment. Existing files are not overwritten unless `--force` is
explicitly supplied to initialization or wrapper generation.

## 2. Record a lesson

Interactive human path:

```bash
failure-memory add --interactive \
  --repo . \
  --config .failure-memory/config.toml \
  --global-vault /read-only/vault
```

Agent/automation path:

```bash
failure-memory add --from-json lesson.json \
  --repo . \
  --config .failure-memory/config.toml \
  --global-vault /read-only/vault
```

Both produce the same canonical registry record. Maintainers may append the same
validated object directly, then run `validate` and `compile` or `ci-check`.

## 3. Compile

```bash
failure-memory validate --repo . --config .failure-memory/config.toml
failure-memory compile --repo . --config .failure-memory/config.toml \
  --global-vault /read-only/vault
failure-memory check --repo . --config .failure-memory/config.toml \
  --global-vault /read-only/vault
```

`compile` writes projections; `check` verifies expected output without adopting
hand-edited generated files as canonical.

## 4. Refresh a deterministic snapshot

```bash
failure-memory refresh preflight --repo . \
  --config .failure-memory/config.toml \
  --global-vault /read-only/vault

failure-memory refresh all --repo . \
  --config .failure-memory/config.toml \
  --global-vault /read-only/vault \
  --generated-at 2026-08-16T00:00:00Z
```

Mirror, graph, and full refresh require an explicit timezone-aware timestamp.
Identical inputs and timestamp produce the deterministic publication target.
Refresh never clones tools, invokes an LLM, or silently falls back.

## 5. Resolve provider context

```bash
failure-memory resolve --repo . \
  --config .failure-memory/config.toml \
  --request request.json

failure-memory validate-fingerprint --repo . \
  --config .failure-memory/config.toml \
  --request request.json \
  --result dev/knowledge/provider/invocation/result.json
```

Provider output is evidence. It does not declare task completion, approval, or a
claim about code correctness.

## 6. CI

```bash
failure-memory ci-check --repo . --config .failure-memory/config.toml
```

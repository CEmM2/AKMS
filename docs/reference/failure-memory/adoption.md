# Adopting akms-failure-memory

`akms-failure-memory` is an optional, independently installable sidecar. Application packages do not import it, AKMS core does not depend on it, and project repositories remain the owners of their registry and generated artifacts.

## Supported contracts

Version 0.1.0 supports the frozen AKMS v2 schema, public AKMS runtime identity `0.6.1`, public-source digest `3a79a11312376a5f203013c87d37b2a695fab895ffa6d47decd2c0ad95f7b828`, repo2md export schema 1, repo2md 0.2.0 at commit `478be35c76325ab1ccea48b69a5ea25b095952a6`, and fixture-pack digest `5d2e398b7baab7045615ccb0e935c2baeae154d21fb4a29ba5498f06687d2d6b`. Preflight requires an executable installed from a verifiable editable checkout, checks its required CLI flags, commit and dirty state, and recomputes every pinned fixture byte. Set `AKMS_REPO2MD_ROOT` to the pinned checkout when it cannot be inferred from editable-install metadata.

## Initialize a project

```bash
failure-memory init --repo . --config .failure-memory/config.toml \
  --repository-id example --node-namespace example-failure
failure-memory doctor --repo . --config .failure-memory/config.toml
```

Review the generated configuration before recording lessons. Every configured path is repository-relative and containment checked. Existing files are not overwritten unless the operator explicitly passes `--force` to initialization or wrapper generation.

## Three equivalent recording paths

Humans can answer prompts:

```bash
failure-memory add --interactive --repo . \
  --config .failure-memory/config.toml --global-vault /read-only/vault
```

Coding agents can submit the same canonical record as JSON:

```bash
failure-memory add --from-json lesson.json --repo . \
  --config .failure-memory/config.toml --global-vault /read-only/vault
```

Maintainers may directly append the identical object to the configured registry. After direct editing, run `failure-memory validate`, then `compile` or `ci-check`. The registry is canonical in all three workflows; the generated nodes and route index are never canonical.

## Compile and refresh

```bash
failure-memory compile --repo . --config .failure-memory/config.toml \
  --global-vault /read-only/vault
failure-memory refresh preflight --repo . --config .failure-memory/config.toml \
  --global-vault /read-only/vault
failure-memory refresh all --repo . --config .failure-memory/config.toml \
  --global-vault /read-only/vault --generated-at 2026-08-11T00:00:00Z
```

Compile, record, refresh, and provider resolution share one reentrant project-local lock. Compiler publication is transactional across generated nodes and routes and rejects symlink components before writing. Refresh runs lessons, mirror, then graph. Mirror, graph, and all refreshes require an explicit timezone-aware `--generated-at`; that value governs atomically published graph metadata, so identical inputs and timestamps produce byte-identical graphs. Graph refresh validates AKMS inputs before publication, preserves any existing graph and state bytes on failure, and does not create an empty `local_state.yaml`; experiential state remains owned by AKMS update operations. The project configuration's `repository_id` is the canonical serialized graph identity and overrides both the AKMS runtime-root basename and any conflicting informational `local_state.yaml` `repo_id`, without rewriting the state file. Refresh never clones, installs, invokes an LLM, or silently falls back. `clean` removes only paths explicitly marked disposable.

## Resolve provider context

Prepare a `failure-memory-provider-request/v1` JSON request, then run:

```bash
failure-memory resolve --repo . --config .failure-memory/config.toml --request request.json
failure-memory validate-fingerprint --repo . --config .failure-memory/config.toml \
  --request request.json --result dev/knowledge/provider/invocation/result.json
```

Use `pre-task` with role `implementer`. Use `post-diff` with `code_reviewer` or `physics_reviewer` and explicit changed paths or a base/head pair. Provider output is evidence only: it emits no task lifecycle, completion, claim, or approval decision.

`refresh_policy = "never"` resolves the existing snapshot without asserting freshness. `refresh_policy = "require-current"` runs toolchain preflight plus compiler and graph drift checks under the shared lock before resolution. Preflight blocks only on an incompatible AKMS schema version or a repo2md that cannot be invoked with the required `export-akms` contract; artifact-identity mismatches (AKMS version, AKMS public-API digest, repo2md version/commit/cleanliness/fixture digest) are returned under `advisories` and do not fail the call. The compiler and graph drift checks remain fail-closed; it requires an explicit read-only `AKMS_GLOBAL_VAULT` path and never refreshes inputs itself.

`validate-fingerprint` reports `current` only when the recomputed fingerprint
matches the recorded one AND the package's deterministic publication
validation (`akms_failure_memory.provider.validate_publication`) accepts the
published graph: `graph.repo_id` must equal the configured `repository_id`,
and the graph's project-namespaced nodes must be exactly the published
generated node files, agreeing on every field the two artifacts share, with
every published `load_with` target present in the graph. Fingerprint
reproducibility alone cannot see these states — a graph published under a
foreign identity, or a graph not rebuilt after nodes were recompiled,
reproduces consistently — so they report `stale` (republish the graph). The
validation compares published artifacts only; it never re-derives compiler or
graph-builder rules, and consumers must inherit it from the package rather
than mirror it.
The freshness rebuild passes through the same canonical graph finalizer used by
refresh, including the validated project `repository_id`. The recorded graph's
identity remains part of the comparison, so changing project identity makes the
old graph stale until an explicit graph refresh publishes the new identity.

## CI

```bash
failure-memory ci-check --repo . --config .failure-memory/config.toml
```

The CI gate is hermetic. It validates configuration and registry shape, checks committed generated bytes without writing them, validates bundled closed schemas, and regenerates the committed Numerix compatibility fixture against immutable digests.

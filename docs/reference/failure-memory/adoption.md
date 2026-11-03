# Adopting akms-failure-memory

`akms-failure-memory` is an optional, independently installable sidecar. Application packages do not import it, AKMS core does not depend on it, and project repositories remain the owners of their registry and generated artifacts.

## Supported contracts

Version 0.1.0 supports the frozen AKMS v2 schema, public AKMS runtime identity `0.6.1`, public-source digest `3a79a11312376a5f203013c87d37b2a695fab895ffa6d47decd2c0ad95f7b828`, repo2md export schema 1, repo2md 0.2.0 at commit `478be35c76325ab1ccea48b69a5ea25b095952a6`, and fixture-pack digest `5d2e398b7baab7045615ccb0e935c2baeae154d21fb4a29ba5498f06687d2d6b`. Preflight requires an executable installed from a verifiable editable checkout, checks its required CLI flags, commit and dirty state, and recomputes every pinned fixture byte. Set `AKMS_REPO2MD_ROOT` to the pinned checkout when it cannot be inferred from editable-install metadata.

## Initialize a project

```bash
failure-memory init --repo . --config .knowledge/failure-memory.toml \
  --repository-id example --node-namespace example-failure
failure-memory doctor --repo . --config .knowledge/failure-memory.toml
```

Review the generated configuration before recording lessons. Every configured path is repository-relative and containment checked. Existing files are not overwritten unless the operator explicitly passes `--force` to initialization or wrapper generation.

`[toolchain].akms_version` and `[toolchain].repo2md_version` each take either a plain version or a PEP 440 specifier set. A value containing any of `<`, `>`, `=`, `!`, `~` or `,` is a specifier set; anything else is a plain version. A plain version must equal the installed version exactly, as before. A specifier set such as `">=0.3.2,<0.4"` matches any installed version inside it, pre-releases within the bounds included. A version outside the pin is reported by preflight as the `akms_version_drift` or `repo2md_version_drift` advisory. A value that is neither a valid version nor a valid specifier set fails configuration loading with `invalid_config`. `failure-memory init` writes a range covering the installed AKMS minor series, `">=<installed>,<<major>.<minor + 1>"`, so a new project does not report drift on its first refresh.

`[toolchain].mirror_provider` chooses the code-mirror exporter. `"builtin"`, which `failure-memory init` writes, runs the `repo-wiki` exporter shipped in akms and needs no other `[toolchain]` keys; its mirrors go to the knowledge directory the graph reads (`.knowledge/code-mirror/`, or `knowledge/code-mirror/` in a repository with only the older directory). `"repo2md"` runs a separately installed `repo-wiki` and requires `repo2md_command`, `repo2md_version`, `repo2md_export_schema_version`, `repo2md_fixture_sha256`, `repo2md_commit` and `repo2md_dirty_policy`. A configuration without `mirror_provider` uses `"repo2md"`, so existing configurations behave as before. To switch an existing project, set `mirror_provider = "builtin"` and delete the `repo2md_*` keys; its config fingerprint changes once.

`[compatibility].lesson_index_version = "failure-lesson-index/v1"`, which `failure-memory init` writes, titles generated nodes from the record instead of the line hint and makes `compile` write a lesson index beside the route index. A configuration without it keeps line-hint titles and writes no index. Adding it to an existing project changes its config fingerprint once and recompiles every node title; node IDs and routes do not change. See [Lesson index](lesson-index.md).

## Three equivalent recording paths

Humans can answer prompts:

```bash
failure-memory add --interactive --repo . \
  --config .knowledge/failure-memory.toml --global-vault /read-only/vault
```

Coding agents can submit the same canonical record as JSON:

```bash
failure-memory add --from-json lesson.json --repo . \
  --config .knowledge/failure-memory.toml --global-vault /read-only/vault
```

Maintainers may directly append the identical object to the configured registry. After direct editing, run `failure-memory validate`, then `compile` or `ci-check`. The registry is canonical in all three workflows; the generated nodes and route index are never canonical.

## Compile and refresh

```bash
failure-memory compile --repo . --config .knowledge/failure-memory.toml \
  --global-vault /read-only/vault
failure-memory refresh preflight --repo . --config .knowledge/failure-memory.toml \
  --global-vault /read-only/vault
failure-memory refresh all --repo . --config .knowledge/failure-memory.toml \
  --global-vault /read-only/vault --generated-at 2026-08-11T00:00:00Z
```

Compile, record, refresh, and provider resolution share one reentrant project-local lock. Compiler publication is transactional across generated nodes and routes and rejects symlink components before writing. Refresh runs lessons, mirror, then graph. Mirror, graph, and all refreshes require an explicit timezone-aware `--generated-at`; that value governs atomically published graph metadata, so identical inputs and timestamps produce byte-identical graphs. Graph refresh validates AKMS inputs before publication, preserves any existing graph and state bytes on failure, and does not create an empty `local_state.yaml`; experiential state remains owned by AKMS update operations. The project configuration's `repository_id` is the canonical serialized graph identity and overrides both the AKMS runtime-root basename and any conflicting informational `local_state.yaml` `repo_id`, without rewriting the state file. Refresh never clones, installs, invokes an LLM, or silently falls back. `clean` removes only paths explicitly marked disposable.

## Move an existing project to `.knowledge/`

A project created with a `knowledge/` directory keeps working there. To move it:

```bash
failure-memory migrate-layout --repo . --check
failure-memory migrate-layout --repo . --global-vault /read-only/vault
```

The directory moves (with `git mv` when tracked), `[paths]` and `generated_warning` follow it, the configuration moves too when it lives inside it, and generated lessons are recompiled. The configuration fingerprint changes once. See [Moving to `.knowledge/`](../akms/user-guide/knowledge-layout.md).

## Resolve provider context

Prepare a `failure-memory-provider-request/v1` JSON request, then run:

```bash
failure-memory resolve --repo . --config .knowledge/failure-memory.toml --request request.json
failure-memory validate-fingerprint --repo . --config .knowledge/failure-memory.toml \
  --request request.json --result .knowledge/provider/invocation/result.json
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
failure-memory ci-check --repo . --config .knowledge/failure-memory.toml
```

The CI gate is hermetic. It validates configuration and registry shape, checks committed generated bytes without writing them, validates bundled closed schemas, and regenerates the committed Numerix compatibility fixture against immutable digests.

# Privacy, providers, and security posture

## Network behavior

**The default core workflow performs no network calls.** Graph compilation,
queries, projections, evidence ingestion, and the `akms` CLI operate entirely
on local files and require no API key, no account, and no credentials.

Network access happens only when you explicitly configure it:

- an LLM provider for the embedded runtime or `akms-learn` expansion
  (via API keys such as `ANTHROPIC_API_KEY`),
- the `nlm` CLI for NotebookLM-grounded generation,
- OpenTelemetry export to an endpoint you configure.

## What leaves your machine

Nothing, unless a provider is configured. When one is:

- Projections/loadouts and node content included in prompts are sent to that
  provider under **its** terms.
- Telemetry spans go only to the endpoint you set (`AKMS_TELEMETRY`,
  OTLP endpoint); the default is no export.

## Untrusted input

Knowledge nodes are Markdown with YAML frontmatter parsed from disk. Treat
vaults and nodes from sources you do not trust as untrusted input:

- **Prompt injection**: node content flows into agent prompts when you use an
  LLM-backed workflow. A malicious node can attempt to steer the agent.
  Review third-party nodes before adding them to a vault you project from.
- **`content_ref` traversal**: node frontmatter references content files by
  relative path. Do not compile vaults from untrusted archives without
  inspecting them; path fields are data, not code, but they select which
  files are read into prompts and packets.
- **YAML**: parsing uses safe loaders; still, prefer reviewing files you did
  not author.

## External binaries

Optional paths shell out to external CLIs (`qmd`, `nlm`, `claude`, `codex`)
found on `PATH`. AKMS never downloads or installs binaries itself. Standard
PATH hygiene applies.

## Filesystem boundaries

- The **global vault is read-only** by contract: no automated process modifies
  `~/.claude/akms/nodes/` (override the location with `AKMS_GLOBAL_VAULT`).
  Project-local state lives in the project's `knowledge/` directory.
- Generated artifacts are written under the project tree, and public artifact
  formats avoid embedding absolute home-directory paths.

## Reporting

Security reports: see `SECURITY.md` (private reporting only).

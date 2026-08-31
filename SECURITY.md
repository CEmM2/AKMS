# Security policy

## Supported versions

AKMS is research software published as a preview. Only the most recent release
receives security fixes.

## Reporting a vulnerability

Please report vulnerabilities **privately** via GitHub's security advisories
("Report a vulnerability" on the repository's Security tab), or by email to
<shmuliko@technion.ac.il> if you would rather not use GitHub. Do not open a
public issue for a suspected vulnerability.

You can expect an acknowledgment within a week. This is a best-effort research
project; there is no bug bounty.

## Threat model notes

Consult `docs/privacy-and-providers.md` for the project's security posture,
including:

- The default core workflow performs **no network calls** and requires no
  credentials.
- Knowledge nodes are Markdown/YAML parsed from disk: treat vaults from
  untrusted sources as untrusted input (prompt-injection and path-traversal
  risks are documented there).
- Optional provider integrations (LLM APIs, external CLIs) run only when
  explicitly configured.

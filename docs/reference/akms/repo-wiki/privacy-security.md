# Privacy and security

`repo-wiki` reads your repository and writes derived files next to it. This
page describes what it reads, what it skips, and what it does not do.

## No network, no model

- Scanning, parsing, page generation, indexing, querying and export are local
  operations. None opens a network connection.
- No language model is called. Summaries are built from the symbol's kind,
  location, docstring and detected calls; `query` returns citations into the
  retrieved context rather than generated prose.
- There is no telemetry.
- Remote summary providers are not implemented. Setting `summaries.provider` to
  anything but `local` is refused unless you also set
  `summaries.allow_source_code_upload: true`, and even then the build fails
  because no remote provider exists. Nothing is uploaded either way.
- The one exception is the browser page served by `repo-wiki graph`. It binds
  to `127.0.0.1` by default, but the page itself loads the d3 JavaScript
  library from `cdn.jsdelivr.net`, so your browser makes that request. The
  symbol graph is not sent anywhere.
- Local programs it may run: `git` (`build` reads the current commit hash;
  `export-akms --git-base` lists changed files) and, for the C++ Doxygen
  backend, `doxygen`.

## What is scanned

The scanner walks the repository and decides per file, in this order:

1. A path matching an exclude pattern is skipped without being opened: the
   [built-in patterns](#built-in-exclude-patterns), including the secret and
   credential set, plus anything in `scanner.exclude`. A directory that
   matches is pruned and not entered.
2. A path matching the root `.gitignore` is skipped the same way, when
   `scanner.respect_gitignore` is `true`.
3. A path not matching `scanner.include` is skipped.
4. A file over `scanner.max_file_size_kb` is skipped.
5. A file whose first 8 KiB contains a NUL byte or is not valid UTF-8 is
   skipped as binary.

`repo-wiki scan --json` lists every skipped path with its reason.

### Symbolic links are never followed

A symbolic link is never read, whether it points at a file or a directory and
whether the target is inside or outside the repository. It is recorded as
skipped with reason `symlink`, so a link cannot pull files from outside the
repository into the wiki or into a mirror.

### Built-in exclude patterns

Two sets of patterns apply without being listed in `config.yaml`. The
ordinary defaults:

| Group | Patterns |
|---|---|
| Version control and tool state | `.git/**`, `.repo_wiki/generated/**`, `.repo_wiki/index/**` |
| Environments and caches | `.venv/**`, `venv/**`, `env/**`, `__pycache__/**`, `.mypy_cache/**`, `.pytest_cache/**`, `node_modules/**`, `*.egg-info/**` |
| Build and data output | `dist/**`, `build/**`, `data/**`, `outputs/**`, `checkpoints/**`, `wandb/**` |

The secret and credential set:

| Group | Patterns |
|---|---|
| Environment files | `.env`, `.env.*`, `*.env` |
| Keys and certificates | `*.pem`, `*.key`, `*.p12`, `*.pfx`, `id_rsa`, `id_ed25519`, `id_dsa`, `id_ecdsa` |
| Secret and credential files | `*_secret`, `*_secret.*`, `*_secrets`, `*_secrets.*`, `*.secret`, `*.secrets`, `secrets.yaml`, `secrets.yml`, `secrets.json`, `credentials`, `credentials.*`, `credentials.json`, `credentials.yaml`, `credentials.yml`, `.netrc`, `*.netrc` |

The posture is to skip, not to redact: an excluded file is never opened, so
its contents cannot reach a page, the index or a mirror.

How configuration interacts with them:

- **Your patterns add to the built-in ones.** Patterns in `scanner.exclude`
  are applied in addition to both sets. A `config.yaml` that still lists the
  full pattern list older versions of `init` wrote keeps the same effect:
  duplicates are ignored.
- **`scanner.use_default_excludes: false` drops only the ordinary defaults.**
  The secret and credential set always applies, and no setting removes it.
  It is also matched against the file name at any depth, so
  `config/.env.local` and `deploy/credentials.toml` are skipped too.
- **Secrets inside ordinary source files are not detected.** A hard-coded API
  key in a Python module is read like any other code and appears in the symbol
  page, the search index and any mirror. Use a dedicated secret scanner, such
  as `gitleaks` or `detect-secrets`, before committing or sharing generated
  output.

`repo-wiki scan --json` prints the complete list applied under `exclude`.

In earlier versions a `scanner.exclude` list replaced the built-in
patterns, so a custom list could let secret files in. The next `build` removes
the pages, index entries and IR cache records of files that are now excluded,
and a full `export-akms --prune` removes their mirrors. Deleted index rows can
leave bytes behind in the SQLite file: if a secret was indexed, delete
`.repo_wiki/index/` and run `build` again.

### `.gitignore`

With `scanner.respect_gitignore: true` (the default), the scanner reads only
the `.gitignore` in the repository root. It skips blank lines, comments and
`!` negations, and matches the remaining lines as simple glob patterns, not
with full git semantics. Nested `.gitignore` files, `.git/info/exclude` and
global ignore files are not read. Use `scanner.exclude` for anything that must
never be read.

## What is written

Generated pages contain your source code: symbol pages include the symbol's
text, and mirrors include the complete file. Treat `.repo_wiki/generated/`,
the search index and any exported mirror as having the same sensitivity as the
source. See [Generated files](generated-files.md) for what to keep out of
version control.

## Writes stay where you expect

- `export-akms` writes only beneath `<output>/<knowledge-dir>/code-mirror/`.
  A relative `--output` that resolves outside the repository is refused.
- Mirror source paths must be repository-relative; absolute paths and `..`
  are rejected.
- Mirrors are written through a temporary file and an atomic rename.
- `--prune` and the removal of deleted sources delete only files that carry
  the exporter's own AKMS code-mirror frontmatter.

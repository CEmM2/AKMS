# CLI reference

```bash
failure-memory [--json-errors] <command> ...
```

Successful commands print JSON. Classified failures print a stable error code;
`--json-errors` emits the error as JSON.

## Project lifecycle

### `init`

```bash
failure-memory init [--repo .] [--config .failure-memory/config.toml] \
  [--repository-id <id>] [--node-namespace <namespace>] [--force]
```

### `doctor`

```bash
failure-memory doctor --config <path> [--repo .]
```

### `migrate-check`

```bash
failure-memory migrate-check --config <path> [--repo .]
```

Reports legacy-layout conditions without moving canonical data.

### `generate-wrapper`

```bash
failure-memory generate-wrapper --config <path> --output <path> \
  [--repo .] [--force]
```

## Registry and compiler

### `add`

Choose exactly one source:

```bash
failure-memory add --interactive --config <path> --global-vault <path> [--repo .]
failure-memory add --from-json lesson.json --config <path> \
  --global-vault <path> [--repo .]
```

### `validate`

```bash
failure-memory validate --config <path> [--repo .]
```

### `compile`

```bash
failure-memory compile --config <path> --global-vault <path> \
  [--repo .] [--output-root <path>]
```

### `check`

```bash
failure-memory check --config <path> --global-vault <path> \
  [--repo .] [--output-root <path>]
```

### `ci-check`

```bash
failure-memory ci-check --config <path> [--repo .]
```

## Refresh

```bash
failure-memory refresh <action> \
  --config <path> \
  --global-vault <path> \
  [--repo .] \
  [--phase 1] \
  [--generated-at <timezone-aware-ISO8601>] \
  [--force-lock]
```

Actions: `preflight`, `status`, `lessons`, `mirror`, `graph`, `all`, `clean`.

`clean` removes only paths marked disposable by project configuration.

## Provider

### `resolve`

```bash
failure-memory resolve --config <path> --request request.json [--repo .]
```

### `validate-fingerprint`

```bash
failure-memory validate-fingerprint --config <path> \
  --request request.json --result result.json [--repo .]
```

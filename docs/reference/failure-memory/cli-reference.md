# CLI reference

```bash
failure-memory [--json-errors] <command> ...
```

Successful commands print JSON. Classified failures print a stable error code;
`--json-errors` emits the error as JSON.

## Project lifecycle

`--config` is optional on every command. When omitted it defaults to
`<repo>/.failure-memory/config.toml`, the file `init` writes, so after `init`
most commands need only `--repo`. An explicit `--config` is read as given.

### `init`

```bash
failure-memory init [--repo .] [--config .failure-memory/config.toml] \
  [--repository-id <id>] [--node-namespace <namespace>] [--force]
```

### `doctor`

```bash
failure-memory doctor [--config <path>] [--repo .]
```

### `migrate-check`

```bash
failure-memory migrate-check [--config <path>] [--repo .]
```

Reports legacy-layout conditions without moving canonical data.

### `generate-wrapper`

```bash
failure-memory generate-wrapper [--config <path>] --output <path> \
  [--repo .] [--force]
```

## Registry and compiler

### `registry migrate`

```bash
failure-memory registry migrate --to 2 [--check] [--config <path>] [--repo .]
```

`--to` accepts only `2`. Schema 2 is opt-in: the command splits a schema 1
registry file into a sibling directory (`lessons.json` becomes `lessons`) of
`<ID>.json` files plus `_registry.json`. It does not allocate new IDs and does
not delete the original file. `previous_registry` in the result is that file.
`--check` compiles both forms in a temporary directory outside the repository
and writes nothing. There is no `--global-vault`. This is not `migrate-check`.

### `add`

Choose exactly one source:

```bash
failure-memory add --interactive [--config <path>] --global-vault <path> [--repo .]
failure-memory add --from-json lesson.json [--config <path>] \
  --global-vault <path> [--repo .]
```

### `validate`

```bash
failure-memory validate [--config <path>] [--repo .]
```

### `compile`

```bash
failure-memory compile [--config <path>] --global-vault <path> \
  [--repo .] [--output-root <path>]
```

### `check`

```bash
failure-memory check [--config <path>] --global-vault <path> \
  [--repo .] [--output-root <path>]
```

### `ci-check`

```bash
failure-memory ci-check [--config <path>] [--repo .]
```

## Refresh

```bash
failure-memory refresh <action> \
  [--config <path>] \
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
failure-memory resolve [--config <path>] --request request.json [--repo .]
```

### `validate-fingerprint`

```bash
failure-memory validate-fingerprint [--config <path>] \
  --request request.json --result result.json [--repo .]
```

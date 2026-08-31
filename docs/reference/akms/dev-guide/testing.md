# Running tests

Test commands should identify the package and scope being exercised. Avoid a
single permanent test count; it becomes false as soon as someone commits a
useful test, which is an oddly self-defeating quality metric.

## Core

```bash
uv run --project Packages/AKMS pytest Packages/AKMS/tests/akms -q
uv run --project Packages/AKMS pytest Packages/AKMS/tests/e2e -q
uv run --project Packages/AKMS pytest Packages/AKMS/tests/plan_tests -q
```

Markers declared by the core package include `unit`, `integration`,
`regression`, `baseline`, and `e2e`.

## Failure memory

```bash
uv run --project Packages/FailureMemory pytest Packages/FailureMemory/tests -q
```

## akms-learn

```bash
uv run --project packages/akms_learn pytest \
  packages/akms_learn/tests -q
```

## Node generation

```bash
uv run --project Packages/AKMS_nodes_gen pytest \
  Packages/AKMS_nodes_gen/tests -q
```

## compmech reference pack

```bash
uv run --project packages/compmech_reference_pack pytest \
  packages/compmech_reference_pack/tests -q
```

The `slow` marker covers the Taichi-paying verification path.

## Documentation contract

```bash
python tools/check_docs_contract.py
uv run --group docs mkdocs build --strict
```

## External E2E

Provider E2E tests are opt-in and require their documented pinned executable and
environment variables. Keep default CI hermetic; do not silently skip the
contract being claimed by a release artifact.

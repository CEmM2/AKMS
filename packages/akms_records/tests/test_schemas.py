"""Schema registry rules: refused references, local $defs, format, digests, rules."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from akms_records import RecordsError
from akms_records.canonical import digest
from akms_records.schemas import (
    DIALECT,
    load_template,
    render_template,
    static_scan,
    template_names,
    validate_instance,
)

TEMPLATES = [
    "decision",
    "experiment-observation",
    "failed-approach",
    "idea",
    "preference",
    "research-finding",
    "successful-approach",
    "workflow-lesson",
]


def schema_with(prop: dict, *, name: str = "note", **extra) -> dict:
    return {
        "$schema": DIALECT,
        "type": "object",
        "properties": {"text": {"type": "string"}, "x": prop},
        "x-akms-records": {"name": name, "version": 1},
        **extra,
    }


def test_builtin_templates_are_plain_schema_files(make_store):
    assert template_names() == TEMPLATES
    store = make_store()
    for name in TEMPLATES:
        registered, new = store.register_schema(load_template(name), actor="t")
        assert new and registered.ref == f"{name}/v1"
        assert registered.rules["summary_template"]
    again, new = store.register_schema(load_template("decision"), actor="t")
    assert not new and again.ref == "decision/v1"


@pytest.mark.parametrize(
    ("ref", "kind"),
    [
        ("http://example.com/s.json", "remote"),
        ("https://example.com/s.json", "remote"),
        ("file:///etc/passwd", "file"),
        ("other.json", "non-local"),
    ],
)
def test_non_local_refs_are_refused_at_registration(make_store, no_network, ref, kind):
    store = make_store()
    with pytest.raises(RecordsError) as caught:
        store.register_schema(schema_with({"$ref": ref}), actor="t")
    assert caught.value.code == "schema_ref_refused"
    assert f"{kind} reference" in str(caught.value)
    assert no_network == []
    assert not store.schemas.refs()


def test_unreached_remote_ref_is_still_refused_statically():
    lazy = schema_with({"$ref": "https://example.com/x.json"})
    assert static_scan(lazy)  # validation alone would never resolve it


@pytest.mark.parametrize(
    "schema",
    [
        {"$id": "https://example.com/root.json", "type": "object"},
        {"$schema": "https://example.com/evil", "type": "object"},
        {"type": "object", "properties": {"a": {"$schema": DIALECT}}},
        {"type": "object", "$vocabulary": {}},
        {"type": "object", "properties": {"a": {"$dynamicRef": "https://x/y"}}},
    ],
)
def test_id_dialect_and_vocabulary_are_refused(schema):
    assert static_scan(schema)


@pytest.mark.parametrize(
    "uri",
    ["http://example.com/s.json", "https://example.com/s.json", "file:///tmp/s.json"],
)
def test_validation_never_resolves_remote_refs(no_network, tmp_path: Path, uri):
    """Even a schema that skipped the scan cannot fetch or read a reference."""
    target = tmp_path / "s.json"
    target.write_text(json.dumps({"type": "integer"}), encoding="utf-8")
    if uri.startswith("file:"):
        uri = target.resolve().as_uri()
    with pytest.raises(RecordsError) as caught:
        validate_instance({"$ref": uri}, "not-an-int", ref="raw/v1")
    assert caught.value.code == "schema_ref_refused"
    assert no_network == []


def test_local_defs_work(make_store, doc):
    store = make_store()
    store.register_schema(load_template("experiment-observation"), actor="t")
    ok = {
        "schema_ref": "experiment-observation/v1",
        "payload": {
            "experiment": "mesh study",
            "observation": "converged",
            "measurements": [{"name": "error", "value": 0.01, "unit": "1"}],
        },
    }
    rid = store.create(ok, actor="t").record_id
    assert store.get(rid).summary == "mesh study: converged"
    bad = json.loads(json.dumps(ok))
    bad["payload"]["measurements"] = [{"name": "error", "value": "high"}]
    with pytest.raises(RecordsError) as caught:
        store.create(bad, actor="t")
    assert caught.value.code == "payload_invalid"
    assert caught.value.details["errors"][0]["path"] == "/measurements/0/value"


def test_format_is_an_annotation_only(make_store):
    store = make_store()
    schema = schema_with({"type": "string", "format": "email"})
    schema["x-akms-records"]["rules"] = {"summary_template": "{text}"}
    store.register_schema(schema, actor="t")
    rid = store.create(
        {"schema_ref": "note/v1", "payload": {"text": "hi", "x": "not-an-email"}},
        actor="t",
    ).record_id
    assert store.get(rid).payload["x"] == "not-an-email"


def test_tampered_schema_is_refused(store, doc):
    path = store.schemas.root / "decision" / "v1" / "schema.json"
    original = path.read_bytes()
    path.write_text(json.dumps(json.loads(original), indent=8), encoding="utf-8")
    assert store.schemas.get("decision/v1")  # whitespace only: same digest
    schema = json.loads(original)
    schema["properties"]["decision"]["maxLength"] = 3
    path.write_text(json.dumps(schema), encoding="utf-8")
    with pytest.raises(RecordsError) as caught:
        store.schemas.get("decision/v1")
    assert caught.value.code == "schema_tampered"
    with pytest.raises(RecordsError) as caught:
        store.create(doc(), actor="t")
    assert caught.value.code == "schema_tampered"
    report = store.doctor(fix=False)
    assert "decision/v1" in report["schema_errors"] and report["status"] == "error"


def test_digest_is_canonical():
    schema = load_template("idea")
    reordered = dict(reversed(list(schema.items())))
    assert digest(schema) == digest(reordered)
    assert digest({"const": 1}) != digest({"const": 1.0})


def test_changed_content_needs_a_new_version(store):
    changed = load_template("decision")
    changed["properties"]["decision"]["maxLength"] = 500
    with pytest.raises(RecordsError) as caught:
        store.register_schema(changed, actor="t")
    assert caught.value.code == "schema_exists"
    changed["x-akms-records"]["version"] = 2
    registered, new = store.register_schema(changed, actor="t")
    assert new and registered.ref == "decision/v2"
    assert store.schemas.resolve_ref("decision") == "decision/v2"


def test_schema_may_not_declare_envelope_keys(make_store):
    schema = schema_with({"type": "string"})
    schema["properties"]["summary"] = {"type": "string"}
    with pytest.raises(RecordsError) as caught:
        make_store().register_schema(schema, actor="t")
    assert caught.value.code == "envelope_shadow"


@pytest.mark.parametrize(
    "rules",
    [
        {"label": "/missing"},
        {"search_text": ["text"]},
        {"summary_template": "{text.upper}"},
        {"summary_template": "{text!r}"},
        {"summary_template": "{missing}"},
        {"summary_template": "unbalanced {"},
        {"time_field": "/x"},  # x is a number below
        {"run": "rm -rf /"},
    ],
)
def test_rules_are_declarative_and_checked(make_store, rules):
    schema = schema_with({"type": "number"})
    schema["x-akms-records"]["rules"] = rules
    with pytest.raises(RecordsError) as caught:
        make_store().register_schema(schema, actor="t")
    assert caught.value.code == "invalid_rules"


def test_template_rendering():
    payload = {"a": "one", "b": ["x", "y"], "n": 2, "deep": {"k": "v"}}
    assert render_template("{a} | {b} | {n} | {/deep/k} | {{lit}}", payload) == (
        "one | x, y | 2 | v | {lit}"
    )
    assert render_template("{missing}  text", payload) == "text"


def test_name_and_version_can_come_from_the_command(make_store):
    schema = {
        "$schema": DIALECT,
        "type": "object",
        "properties": {"t": {"type": "string"}},
    }
    store = make_store()
    registered, _ = store.register_schema(schema, actor="t", name="plain", version=3)
    assert registered.ref == "plain/v3"
    with pytest.raises(RecordsError):
        store.register_schema(schema, actor="t")  # no name anywhere

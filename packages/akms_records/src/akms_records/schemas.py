"""The per-store schema registry.

Schemas live inside the store root::

    <root>/_schemas/<name>/v<N>/schema.json        the schema, canonical JSON
    <root>/_schemas/<name>/v<N>/registration.json  ref, digest, who and when
    <root>/_schemas/<name>/v<N>/_rules.json        extraction rules (optional)
    <root>/_schemas/<name>/v<N>/_rules_log.jsonl   every rules change

A schema is JSON Schema Draft 2020-12 describing a record's ``payload``. Its
digest is the SHA-256 of its canonical JSON, recorded at registration and
copied into every record written against it. Loading a schema recomputes the
digest; a schema whose content no longer matches is refused.

**Digest boundary.** The digest covers the whole schema document, including
the ``name``, ``version``, ``title`` and ``description`` of its
``x-akms-records`` block, *except* ``x-akms-records.rules``. Rules only steer
derived artifacts (search text, label, time field, summary template), so they
are stored beside the schema with their own digest and change log, and
changing them never needs a new schema version or touches existing records.

Reference resolution never leaves the schema. Every validator is built with an
explicit :class:`referencing.Registry` whose retrieve hook refuses every URI,
and registration first runs a static scan that rejects any ``$ref`` or
``$dynamicRef`` that is not a local ``#...`` pointer, any ``$id``, and any
dialect other than 2020-12. ``format`` is an annotation only: no format
checker runs, so a record validates the same way on every machine.

A schema may carry an ``x-akms-records`` block with its name, version and
declarative extraction rules (search-text fields, label, time field and
summary template). Registration moves the rules out of the stored schema and
beside it. The rules are data: nothing in a schema or its rules is executed.
"""

from __future__ import annotations

import functools
import importlib.resources
import os
import re
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path
from types import SimpleNamespace
from typing import Any

from akms_records.canonical import canonical_bytes, compact_line, digest, loads_strict
from akms_records.envelope import ENVELOPE_KEYS, MAX_SUMMARY
from akms_records.errors import NotFound, RecordsError
from akms_records.fsio import append_line, replace_file, write_exclusive

DIALECT = "https://json-schema.org/draft/2020-12/schema"
REGISTRY_DIRNAME = "_schemas"
EXTENSION_KEY = "x-akms-records"
REGISTRATION_FORMAT = "akms-records-schema-registration/v1"
RULES_FORMAT = "akms-records-rules/v1"
RULES_FILE = "_rules.json"
RULES_LOG = "_rules_log.jsonl"
NAME_RE = re.compile(r"[a-z][a-z0-9-]{0,63}")
REF_RE = re.compile(r"([a-z][a-z0-9-]{0,63})/v([1-9][0-9]{0,5})")
RESERVED_NAME = "consolidation"  # the built-in summary schema
RESERVED_LESSON_NAME = "failure-lesson"  # the built-in failure-lesson schema
RULE_KEYS = ("search_text", "label", "time_field", "summary_template")
_PLACEHOLDER = re.compile(r"\{([^{}]*)\}")
_IDENT = re.compile(r"[A-Za-z_][A-Za-z0-9_]*")
MAX_ERRORS = 20


@functools.cache
def _validation() -> SimpleNamespace:
    """The JSON Schema machinery, imported on first use.

    It is most of this package's import time, and recall and wake rarely need it, so
    a command that only reads does not pay for it.

    ``refusing`` resolves nothing. Passing it explicitly matters: without a registry,
    jsonschema fetches http(s) references and reads file: references. ``meta`` holds
    the bundled metaschemas, and nothing else, for checking a schema itself.
    """
    import jsonschema_specifications  # the bundled Draft 2020-12 metaschemas
    from jsonschema import Draft202012Validator
    from referencing import Registry
    from referencing.exceptions import NoSuchResource, Unresolvable

    def refuse(uri: str) -> Any:
        raise NoSuchResource(ref=uri)

    refusing: Registry[Any] = Registry(retrieve=refuse)
    return SimpleNamespace(
        Validator=Draft202012Validator,
        Unresolvable=Unresolvable,
        refusing=refusing,
        meta=refusing.combine(jsonschema_specifications.REGISTRY),
    )


def _schema_error(message: str, *, code: str = "invalid_schema", **details: Any):
    return RecordsError(message, code=code, details=details or None)


def parse_ref(ref: str) -> tuple[str, int]:
    match = REF_RE.fullmatch(ref) if isinstance(ref, str) else None
    if match is None:
        raise RecordsError(
            f"invalid schema ref {ref!r}: expected <name>/v<N>",
            code="invalid_schema_ref",
        )
    return match.group(1), int(match.group(2))


def _escape(token: str) -> str:
    return token.replace("~", "~0").replace("/", "~1")


def static_scan(schema: Any) -> list[str]:
    """Problems that make ``schema`` unsafe to register, as readable strings.

    Only local ``#...`` references are allowed. ``$id`` is refused anywhere
    (it would change the base URI for relative references), ``$schema`` only
    at the root and only as Draft 2020-12, and ``$vocabulary`` everywhere.
    """
    problems: list[str] = []

    def walk(node: Any, pointer: str) -> None:
        if isinstance(node, dict):
            for key, value in node.items():
                where = f"{pointer}/{_escape(key)}"
                if key in ("$ref", "$dynamicRef"):
                    if not isinstance(value, str) or not value.startswith("#"):
                        text = value if isinstance(value, str) else repr(value)
                        lowered = text.lower()
                        if lowered.startswith(("http:", "https:")):
                            kind = "remote"
                        elif lowered.startswith("file:"):
                            kind = "file"
                        else:
                            kind = "non-local"
                        problems.append(f"{where}: {kind} reference {text!r} refused")
                elif key == "$id":
                    problems.append(f"{where}: $id is not allowed")
                elif key == "$vocabulary":
                    problems.append(f"{where}: $vocabulary is not allowed")
                elif key == "$schema" and (pointer != "" or value != DIALECT):
                    problems.append(f"{where}: only a root $schema of {DIALECT}")
                walk(value, where)
        elif isinstance(node, list):
            for index, value in enumerate(node):
                walk(value, f"{pointer}/{index}")

    walk(schema, "")
    return problems


def _pointer_tokens(pointer: Any) -> list[str]:
    if not isinstance(pointer, str) or not pointer.startswith("/") or pointer == "/":
        raise _schema_error(
            f"rule field {pointer!r} must be a JSON pointer such as /decision",
            code="invalid_rules",
        )
    tokens = pointer[1:].split("/")
    out = []
    for token in tokens:
        if re.search(r"~(?![01])", token) or not token:
            raise _schema_error(
                f"rule field {pointer!r} is not a valid JSON pointer",
                code="invalid_rules",
            )
        out.append(token.replace("~1", "/").replace("~0", "~"))
    return out


def _deref(root: dict[str, Any], node: Any) -> Any:
    for _ in range(32):
        if not isinstance(node, dict):
            return node
        ref = node.get("$ref")
        if not isinstance(ref, str) or not ref.startswith("#"):
            return node
        target: Any = root
        if ref not in ("#", "#/"):
            if not ref.startswith("#/"):
                return node  # an anchor; not followed for rule checks
            for token in ref[2:].split("/"):
                token = token.replace("~1", "/").replace("~0", "~")
                if isinstance(target, dict) and token in target:
                    target = target[token]
                elif isinstance(target, list) and token.isdigit():
                    target = target[int(token)] if int(token) < len(target) else None
                else:
                    return None
        node = target
    return node


def _property_schema(root: dict[str, Any], tokens: list[str]) -> Any:
    node: Any = root
    for token in tokens:
        node = _deref(root, node)
        if not isinstance(node, dict):
            return None
        properties = node.get("properties")
        if not isinstance(properties, dict) or token not in properties:
            return None
        node = properties[token]
    return _deref(root, node)


def _check_template(root: dict[str, Any], template: Any) -> None:
    if not isinstance(template, str) or not template.strip():
        raise _schema_error(
            "summary_template must be non-empty text", code="invalid_rules"
        )
    stripped = template.replace("{{", "").replace("}}", "")
    for match in _PLACEHOLDER.finditer(stripped):
        _placeholder_tokens(root, match.group(1))
    leftover = _PLACEHOLDER.sub("", stripped)
    if "{" in leftover or "}" in leftover:
        raise _schema_error(
            "summary_template has an unbalanced brace; write {{ or }} for a "
            "literal brace",
            code="invalid_rules",
        )


def _placeholder_tokens(root: dict[str, Any] | None, inner: str) -> list[str]:
    if _IDENT.fullmatch(inner):
        tokens = [inner]
    elif inner.startswith("/"):
        tokens = _pointer_tokens(inner)
    else:
        raise _schema_error(
            f"summary_template placeholder {{{inner}}} must be a payload field "
            "name or a JSON pointer; no attributes, indexes or format specs",
            code="invalid_rules",
        )
    if root is not None and _property_schema(root, tokens) is None:
        raise _schema_error(
            f"summary_template placeholder {{{inner}}} names no declared property",
            code="invalid_rules",
        )
    return tokens


def check_rules(schema: dict[str, Any], rules: Any) -> dict[str, Any]:
    """Validate the declarative extraction rules against the schema."""
    if rules is None:
        return {}
    if not isinstance(rules, dict):
        raise _schema_error("rules must be an object", code="invalid_rules")
    unknown = sorted(set(rules) - set(RULE_KEYS))
    if unknown:
        raise _schema_error(
            "unknown rules: " + ", ".join(unknown), code="invalid_rules"
        )
    if "search_text" in rules:
        fields = rules["search_text"]
        if not isinstance(fields, list) or len(set(map(str, fields))) != len(fields):
            raise _schema_error(
                "search_text must be a list of distinct JSON pointers",
                code="invalid_rules",
            )
        for pointer in fields:
            if _property_schema(schema, _pointer_tokens(pointer)) is None:
                raise _schema_error(
                    f"search_text field {pointer} names no declared property",
                    code="invalid_rules",
                )
    for key in ("label", "time_field"):
        if key in rules:
            target = _property_schema(schema, _pointer_tokens(rules[key]))
            if target is None:
                raise _schema_error(
                    f"{key} {rules[key]} names no declared property",
                    code="invalid_rules",
                )
            if key == "time_field" and isinstance(target, dict):
                declared = target.get("type")
                if declared is not None and declared != "string":
                    raise _schema_error(
                        f"time_field {rules[key]} must be a string property",
                        code="invalid_rules",
                    )
    if "summary_template" in rules:
        _check_template(schema, rules["summary_template"])
    return dict(rules)


def _lookup(payload: Any, tokens: list[str]) -> Any:
    node = payload
    for token in tokens:
        if isinstance(node, dict) and token in node:
            node = node[token]
        elif isinstance(node, list) and token.isdigit() and int(token) < len(node):
            node = node[int(token)]
        else:
            return None
    return node


def _as_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, (int, float)):
        return repr(value)
    if isinstance(value, list):
        return ", ".join(_as_text(item) for item in value)
    return ""


def pointer_value(payload: Any, pointer: Any) -> Any:
    """The payload value a rules pointer names, or ``None`` when absent."""
    try:
        tokens = _pointer_tokens(pointer)
    except RecordsError:
        return None
    return _lookup(payload, tokens)


def pointer_text(payload: Any, pointer: Any) -> str:
    """The text a rules pointer gives ``payload``, as summary templates render it."""
    return _as_text(pointer_value(payload, pointer))


def render_template(template: str, payload: dict[str, Any]) -> str:
    """Fill ``{field}`` and ``{/pointer}`` placeholders from ``payload``.

    Values are inserted as plain text: strings as written, numbers and
    booleans in JSON spelling, arrays joined with ", ". Objects and missing
    fields render as nothing. Whitespace is collapsed to single spaces.
    """
    out: list[str] = []
    index = 0
    while index < len(template):
        char = template[index]
        if template.startswith("{{", index) or template.startswith("}}", index):
            out.append(char)
            index += 2
            continue
        if char == "{":
            end = template.index("}", index)
            tokens = _placeholder_tokens(None, template[index + 1 : end])
            out.append(_as_text(_lookup(payload, tokens)))
            index = end + 1
            continue
        out.append(char)
        index += 1
    text = " ".join("".join(out).split())
    return text[:MAX_SUMMARY]


def split_rules(schema: Any) -> tuple[Any, Any]:
    """Return ``schema`` without ``x-akms-records.rules``, and those rules.

    The rules are ``None`` when the schema declares none. An extension block
    that only held rules is dropped entirely, so the digest is the same as
    for the schema written without it.
    """
    if not isinstance(schema, dict):
        return schema, None
    block = schema.get(EXTENSION_KEY)
    if not isinstance(block, dict) or "rules" not in block:
        return schema, None
    rest = {key: value for key, value in block.items() if key != "rules"}
    stripped = {key: value for key, value in schema.items() if key != EXTENSION_KEY}
    if rest:
        stripped[EXTENSION_KEY] = rest
    return stripped, block["rules"]


def schema_digest(schema: Any) -> str:
    """The schema digest: canonical JSON without ``x-akms-records.rules``."""
    return digest(split_rules(schema)[0])


def render_summary(rules: dict[str, Any], payload: dict[str, Any]) -> str | None:
    """The summary that ``rules``' template gives ``payload``, if any."""
    template = rules.get("summary_template")
    if not isinstance(template, str):
        return None
    return render_template(template, payload) or None


@dataclass(frozen=True)
class RegisteredSchema:
    """A schema as registered in one store (without its extraction rules)."""

    name: str
    version: int
    schema: dict[str, Any]
    schema_sha256: str
    registered_at: str
    registered_by: str

    @property
    def ref(self) -> str:
        return f"{self.name}/v{self.version}"

    @property
    def extension(self) -> dict[str, Any]:
        block = self.schema.get(EXTENSION_KEY)
        return block if isinstance(block, dict) else {}

    def validate_payload(self, payload: Any) -> None:
        validate_instance(self.schema, payload, ref=self.ref)

    def to_json(self, *, include_schema: bool = False) -> dict[str, Any]:
        out: dict[str, Any] = {
            "schema_ref": self.ref,
            "schema_sha256": self.schema_sha256,
            "registered_at": self.registered_at,
            "registered_by": self.registered_by,
            "title": self.extension.get("title", self.schema.get("title")),
        }
        if include_schema:
            out["schema"] = self.schema
        return out


@dataclass(frozen=True)
class Registration:
    """The outcome of :meth:`SchemaRegistry.register`.

    ``rules`` is ``"set"`` (rules were offered and stored), ``"unchanged"``
    (the same rules were already stored), ``"kept"`` (different rules were
    already stored and were left alone; use ``schema rules set``) or
    ``"none"`` (no rules offered).
    """

    schema: RegisteredSchema
    new: bool
    rules: str


def validate_instance(schema: dict[str, Any], instance: Any, *, ref: str) -> None:
    """Validate ``instance``; references are never fetched, formats never checked."""
    validation = _validation()
    validator = validation.Validator(
        schema, registry=validation.refusing, format_checker=None
    )
    try:
        errors = sorted(
            validator.iter_errors(instance),
            key=lambda error: (list(map(str, error.absolute_path)), error.message),
        )
    except validation.Unresolvable as exc:
        raise RecordsError(
            f"{ref}: schema reference refused: {exc}",
            code="schema_ref_refused",
        ) from None
    if errors:
        shown = [
            {
                "path": "/"
                + "/".join(_escape(str(part)) for part in error.absolute_path),
                "message": error.message,
            }
            for error in errors[:MAX_ERRORS]
        ]
        raise RecordsError(
            f"payload does not match {ref}: {len(errors)} error(s)",
            code="payload_invalid",
            details={"errors": shown, "count": len(errors)},
        )


def check_schema_document(
    schema: Any, *, name: str | None = None, version: int | None = None
) -> tuple[str, int]:
    """Check a schema for registration and return its ``(name, version)``."""
    if not isinstance(schema, dict):
        raise _schema_error("a schema must be a JSON object")
    problems = static_scan(schema)
    if problems:
        raise _schema_error(
            "schema refused: " + "; ".join(problems),
            code="schema_ref_refused",
            problems=problems,
        )
    validation = _validation()
    meta = validation.Validator(
        validation.Validator.META_SCHEMA,
        registry=validation.meta,
        format_checker=None,
    )
    try:
        meta_errors = [error.message for error in meta.iter_errors(schema)]
    except validation.Unresolvable as exc:
        raise _schema_error(f"schema refused: {exc}", code="schema_ref_refused")
    if meta_errors:
        raise _schema_error(
            "not a valid Draft 2020-12 schema: " + "; ".join(meta_errors[:5])
        )
    if schema.get("type") != "object":
        raise _schema_error('a record schema must declare "type": "object"')
    properties = schema.get("properties", {})
    shadowed = sorted(set(properties) & set(ENVELOPE_KEYS))
    if shadowed:
        raise RecordsError(
            "schema properties shadow envelope keys: " + ", ".join(shadowed),
            code="envelope_shadow",
            details={"keys": shadowed},
        )
    block = schema.get(EXTENSION_KEY, {})
    if not isinstance(block, dict):
        raise _schema_error(f"{EXTENSION_KEY} must be an object")
    unknown = sorted(set(block) - {"name", "version", "title", "description", "rules"})
    if unknown:
        raise _schema_error(f"unknown {EXTENSION_KEY} keys: " + ", ".join(unknown))
    declared_name, declared_version = block.get("name"), block.get("version")
    if name is not None and declared_name is not None and name != declared_name:
        raise _schema_error(
            f"--name {name!r} differs from the schema's {declared_name!r}"
        )
    if (
        version is not None
        and declared_version is not None
        and version != declared_version
    ):
        raise _schema_error(
            f"--version {version} differs from the schema's {declared_version}"
        )
    final_name = name if name is not None else declared_name
    final_version = version if version is not None else declared_version
    if not isinstance(final_name, str) or not NAME_RE.fullmatch(final_name):
        raise _schema_error(
            f"schema name {final_name!r} must be lowercase letters, digits and -, "
            "starting with a letter (give --name or x-akms-records.name)"
        )
    if type(final_version) is not int or final_version < 1 or final_version > 999999:
        raise _schema_error(
            f"schema version {final_version!r} must be a positive integer "
            "(give --version or x-akms-records.version)"
        )
    check_rules(schema, block.get("rules"))
    return final_name, final_version


class SchemaRegistry:
    """Schemas registered in one store root, with their extraction rules."""

    def __init__(self, store_root: str | Path) -> None:
        self.root = Path(store_root) / REGISTRY_DIRNAME

    def _dir(self, name: str, version: int) -> Path:
        return self.root / name / f"v{version}"

    def rules_path(self, ref: str) -> Path | None:
        """Where ``ref``'s rules file would be, or ``None`` for a malformed ref."""
        try:
            name, version = parse_ref(ref)
        except RecordsError:
            return None
        return self._dir(name, version) / RULES_FILE

    def register(
        self,
        schema: Any,
        *,
        actor: str,
        at: str,
        name: str | None = None,
        version: int | None = None,
        rules: Any = None,
    ) -> Registration:
        """Register ``schema`` and, if offered, its extraction rules.

        Rules come from the schema's ``x-akms-records.rules`` or from
        ``rules``, not both. Registering the same schema content again is a
        no-op; different content under an existing ``name/vN`` is refused, so
        publish a new version. Rules never take part in that comparison.
        """
        stripped, block_rules = split_rules(schema)
        if rules is not None and block_rules is not None:
            raise _schema_error(
                "give extraction rules either in the schema's x-akms-records "
                "block or as options, not both",
                code="invalid_rules",
            )
        offered = rules if rules is not None else block_rules
        final_name, final_version = check_schema_document(
            stripped, name=name, version=version
        )
        if offered is not None:
            check_rules(stripped, offered)
        ref = f"{final_name}/v{final_version}"
        sha = digest(stripped)
        if final_name == RESERVED_NAME:
            from akms_records.citations import builtin_digest

            if final_version != 1 or sha != builtin_digest():
                raise RecordsError(
                    f"the schema name {RESERVED_NAME!r} is reserved for the "
                    "built-in summary schema consolidation/v1",
                    code="reserved_schema",
                )
        if final_name == RESERVED_LESSON_NAME:
            from akms_records.citations import lesson_digest

            if final_version != 1 or sha != lesson_digest():
                raise RecordsError(
                    f"the schema name {RESERVED_LESSON_NAME!r} is reserved for the "
                    "built-in lesson schema failure-lesson/v1",
                    code="reserved_schema",
                )
        target = self._dir(final_name, final_version)
        wrote = False
        if (target / "registration.json").exists():
            existing = self.get(ref)
            if existing.schema_sha256 != sha:
                raise RecordsError(
                    f"{existing.ref} is already registered with a different digest; "
                    "register the change as a new version",
                    code="schema_exists",
                    details={
                        "schema_ref": existing.ref,
                        "registered_sha256": existing.schema_sha256,
                        "offered_sha256": sha,
                    },
                )
        else:
            target.mkdir(parents=True, exist_ok=True)
            try:
                write_exclusive(target, "schema.json", canonical_bytes(stripped))
            except FileExistsError:
                # A registration interrupted between its two files, or a racing one.
                present = loads_strict((target / "schema.json").read_bytes())
                if digest(present) != sha:
                    raise RecordsError(
                        f"{ref}: a different schema file is already present",
                        code="schema_exists",
                    ) from None
            registration = {
                "format": REGISTRATION_FORMAT,
                "schema_ref": ref,
                "schema_sha256": sha,
                "registered_at": at,
                "registered_by": actor,
            }
            wrote = True
            try:
                write_exclusive(
                    target, "registration.json", canonical_bytes(registration)
                )
            except FileExistsError:
                wrote = False  # a concurrent registration of the same ref won
        found = self.get(ref)
        if found.schema_sha256 != sha:
            raise RecordsError(
                f"{found.ref} is already registered with a different digest",
                code="schema_exists",
            )
        status = "none"
        if offered is not None:
            current = self.rules_record(ref)
            if current is None:
                self.set_rules(ref, offered, actor=actor, at=at)
                status = "set"
            elif current["rules_sha256"] == digest(offered):
                status = "unchanged"
            else:
                status = "kept"
        return Registration(schema=found, new=wrote, rules=status)

    def resolve_ref(self, ref_or_name: str) -> str:
        """``name/vN`` as given, or the newest registered version of ``name``."""
        if REF_RE.fullmatch(ref_or_name or ""):
            return ref_or_name
        if not isinstance(ref_or_name, str) or not NAME_RE.fullmatch(ref_or_name):
            raise RecordsError(
                f"invalid schema ref {ref_or_name!r}", code="invalid_schema_ref"
            )
        versions = self.versions(ref_or_name)
        if not versions:
            raise NotFound(
                f"schema {ref_or_name} is not registered", code="schema_not_found"
            )
        return f"{ref_or_name}/v{versions[-1]}"

    def versions(self, name: str) -> list[int]:
        base = self.root / name
        if not base.is_dir():
            return []
        out = []
        for entry in os.listdir(base):
            match = re.fullmatch(r"v([1-9][0-9]{0,5})", entry)
            if match and (base / entry / "registration.json").is_file():
                out.append(int(match.group(1)))
        return sorted(out)

    def names(self) -> list[str]:
        if not self.root.is_dir():
            return []
        return sorted(
            entry
            for entry in os.listdir(self.root)
            if NAME_RE.fullmatch(entry) and (self.root / entry).is_dir()
        )

    def get(self, ref: str) -> RegisteredSchema:
        """Load a registered schema, refusing one whose digest no longer matches."""
        name, version = parse_ref(ref)
        target = self._dir(name, version)
        registration_path = target / "registration.json"
        schema_path = target / "schema.json"
        if not registration_path.is_file() or not schema_path.is_file():
            raise NotFound(f"schema {ref} is not registered", code="schema_not_found")
        try:
            registration = loads_strict(registration_path.read_bytes())
            schema = loads_strict(schema_path.read_bytes())
        except (ValueError, UnicodeDecodeError) as exc:
            raise RecordsError(
                f"schema {ref}: unreadable registry file: {exc}", code="schema_tampered"
            ) from None
        if (
            not isinstance(registration, dict)
            or registration.get("format") != REGISTRATION_FORMAT
            or registration.get("schema_ref") != ref
            or not isinstance(registration.get("schema_sha256"), str)
        ):
            raise RecordsError(
                f"schema {ref}: malformed registration", code="schema_tampered"
            )
        actual = digest(schema)
        if actual != registration["schema_sha256"]:
            raise RecordsError(
                f"schema {ref} no longer matches its registered digest",
                code="schema_tampered",
                details={
                    "schema_ref": ref,
                    "registered_sha256": registration["schema_sha256"],
                    "actual_sha256": actual,
                },
            )
        if (
            not isinstance(schema, dict)
            or static_scan(schema)
            or split_rules(schema)[1] is not None
        ):
            raise RecordsError(
                f"schema {ref} contains references or rules that are not allowed "
                "in a stored schema",
                code="schema_tampered",
            )
        return RegisteredSchema(
            name=name,
            version=version,
            schema=schema,
            schema_sha256=actual,
            registered_at=str(registration.get("registered_at", "")),
            registered_by=str(registration.get("registered_by", "")),
        )

    def refs(self) -> list[str]:
        return [
            f"{name}/v{version}"
            for name in self.names()
            for version in self.versions(name)
        ]

    def iter_checked(self) -> Iterator[tuple[str, RegisteredSchema | RecordsError]]:
        """Every registered ref with its schema, or the error loading it."""
        for ref in self.refs():
            try:
                yield ref, self.get(ref)
            except RecordsError as exc:
                yield ref, exc

    # ------------------------------------------------------------ rules
    def _rules_dir(self, ref: str) -> Path:
        name, version = parse_ref(ref)
        target = self._dir(name, version)
        if not (target / "registration.json").is_file():
            raise NotFound(f"schema {ref} is not registered", code="schema_not_found")
        return target

    def rules_record(self, ref: str) -> dict[str, Any] | None:
        """The stored rules file of ``ref``, checked against its digest."""
        path = self._rules_dir(ref) / RULES_FILE
        if not path.is_file():
            return None
        try:
            record = loads_strict(path.read_bytes())
        except (ValueError, UnicodeDecodeError) as exc:
            raise RecordsError(
                f"rules of {ref} are unreadable: {exc}", code="rules_invalid"
            ) from None
        if (
            not isinstance(record, dict)
            or record.get("format") != RULES_FORMAT
            or record.get("schema_ref") != ref
            or not isinstance(record.get("rules"), dict)
        ):
            raise RecordsError(f"rules of {ref} are malformed", code="rules_invalid")
        if record.get("rules_sha256") != digest(record["rules"]):
            raise RecordsError(
                f"rules of {ref} no longer match their digest", code="rules_invalid"
            )
        return record

    def rules(self, ref: str) -> dict[str, Any]:
        """The extraction rules of ``ref`` (empty when none are set)."""
        record = self.rules_record(ref)
        return dict(record["rules"]) if record else {}

    def rules_log(self, ref: str) -> list[dict[str, Any]]:
        path = self._rules_dir(ref) / RULES_LOG
        if not path.is_file():
            return []
        entries = []
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                entries.append(loads_strict(line))
            except ValueError as exc:
                raise RecordsError(
                    f"rules log of {ref}, line {number}: {exc}", code="rules_invalid"
                ) from None
        return entries

    def set_rules(self, ref: str, rules: Any, *, actor: str, at: str) -> dict[str, Any]:
        """Validate and store new rules for ``ref``, logging the change.

        Every pointer must name a property the schema declares. The log entry
        is written before the rules file.
        """
        schema = self.get(ref)
        value = check_rules(schema.schema, rules)
        try:
            current = self.rules_record(ref)
            previous = current["rules"] if current else None
        except RecordsError:
            previous = None  # an unreadable rules file is being replaced
        sha = digest(value)
        folder = self._rules_dir(ref)
        entry = {
            "schema_ref": ref,
            "at": at,
            "actor": actor,
            "previous": previous,
            "value": value,
            "rules_sha256": sha,
        }
        append_line(folder / RULES_LOG, compact_line(entry))
        record = {
            "format": RULES_FORMAT,
            "schema_ref": ref,
            "rules": value,
            "rules_sha256": sha,
            "set_at": at,
            "set_by": actor,
        }
        replace_file(folder / RULES_FILE, canonical_bytes(record))
        return {
            "schema_ref": ref,
            "rules": value,
            "rules_sha256": sha,
            "previous": previous,
            "logged": entry,
        }

    def rules_problem(self, ref: str) -> str | None:
        """A problem description when the rules file is bad or disagrees with its log."""
        try:
            record = self.rules_record(ref)
            log = self.rules_log(ref)
        except RecordsError as exc:
            return str(exc)
        if not log:
            return None if record is None else "rules set without a log entry"
        latest = max(log, key=lambda entry: str(entry.get("at", "")))
        if record is None or latest.get("value") != record["rules"]:
            return "the newest rules log entry differs from the current rules"
        return None


def template_names() -> list[str]:
    folder = importlib.resources.files("akms_records") / "templates"
    return sorted(
        entry.name.removesuffix(".schema.json")
        for entry in folder.iterdir()
        if entry.name.endswith(".schema.json")
    )


def load_template(name: str) -> dict[str, Any]:
    if name not in template_names():
        raise NotFound(
            f"no built-in template {name!r}; available: " + ", ".join(template_names()),
            code="template_not_found",
        )
    folder = importlib.resources.files("akms_records") / "templates"
    document = loads_strict((folder / f"{name}.schema.json").read_bytes())
    if not isinstance(document, dict):
        raise RecordsError(f"template {name} is not an object", code="invalid_schema")
    return document


__all__ = [
    "DIALECT",
    "EXTENSION_KEY",
    "RegisteredSchema",
    "Registration",
    "render_summary",
    "schema_digest",
    "split_rules",
    "SchemaRegistry",
    "check_rules",
    "check_schema_document",
    "load_template",
    "parse_ref",
    "render_template",
    "static_scan",
    "template_names",
    "validate_instance",
]

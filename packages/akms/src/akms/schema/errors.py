"""AKMS schema errors."""


class SchemaVersionError(Exception):
    """Raised when akms_schema version doesn't match the expected version."""

    def __init__(self, found: str, expected: str = "v2", path: str | None = None):
        self.found = found
        self.expected = expected
        self.path = path
        loc = f" in {path}" if path else ""
        super().__init__(
            f"Schema version mismatch{loc}: found '{found}', expected '{expected}'"
        )


class SchemaValidationError(Exception):
    """Raised when schema validation fails (missing/invalid fields)."""

    def __init__(self, message: str, path: str | None = None):
        self.path = path
        loc = f" in {path}" if path else ""
        super().__init__(f"Schema validation error{loc}: {message}")

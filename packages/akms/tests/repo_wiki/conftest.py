"""Shared configuration for the repo-wiki tests."""

# `fixtures/` holds sample repositories, some with their own `test_*.py` files.
# They are scanned as data and must not be collected as tests.
collect_ignore = ["fixtures"]

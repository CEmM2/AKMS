"""Package-level tests for Global vault is read-only.

These tests pin the AKMS invariant that ``compile_learning_source`` MUST NOT
write anywhere under ``~/.claude/akms/nodes/`` (the global vault). Plan §1
out-of-scope reminder (the internal plan) forbids any mutation of
the global vault from automated processes.

Three cases together enforce the invariant:

  ``test_global_vault_readonly`` fails compile if any write to
        ``~/.claude/akms/nodes/`` is attempted.

The cases assert the contract from two directions:

  1. After a full compile under a fake ``$HOME``, no file exists below
     ``<fake_home>/.claude/akms/nodes/``.
  2. With ``pathlib.Path.write_text`` / ``write_bytes`` / ``open`` monkey-patched
     to raise on any write under the vault, compile completes without
     tripping the guard — proving the implementation never even attempts a
     vault write.
  3. With ``AKMS_GLOBAL_VAULT`` redirected to a custom tmp path, that path is
     also never written to.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from akms_learn import (
    compile_learning_source,
    fixture_graph,
)


# Default LearningRequest comes from the ``make_request`` conftest fixture.


def _vault_files(vault_root: Path) -> list[Path]:
    """Recursively list any files under ``vault_root`` (returns [] if absent)."""
    if not vault_root.exists():
        return []
    return [p for p in vault_root.rglob("*") if p.is_file()]


class TestGlobalVaultReadOnly:
    """Tests for global vault stays read-only.

    AC covered: 2.
    """

    @pytest.mark.integration
    def test_compile_does_not_write_to_global_vault(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_request
    ) -> None:
        """No file appears under ``<fake_home>/.claude/akms/nodes/`` after compile."""
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir(exist_ok=True)
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.delenv("AKMS_GLOBAL_VAULT", raising=False)

        out_dir = tmp_path / "out"
        result = compile_learning_source(
            request=make_request(),
            graph_slice=fixture_graph(),
            output_dir=out_dir,
        )

        # Compile must have produced its normal artifacts under out_dir …
        assert result.packet_path is not None
        assert result.packet_path.exists()

        # … and NOTHING under the fake home's vault path.
        vault_root = fake_home / ".claude" / "akms" / "nodes"
        offenders = _vault_files(vault_root)
        assert offenders == [], (
            f"compile_learning_source wrote {len(offenders)} files under the "
            f"read-only global vault: {offenders!r}"
        )

    @pytest.mark.integration
    def test_compile_write_attempt_under_vault_raises(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_request
    ) -> None:
        """Vault-write monkey-patch raises on any write; compile must not trip it.

        Patches ``pathlib.Path.write_text`` / ``write_bytes`` / ``open`` so
        that any call whose resolved target sits under
        ``<fake_home>/.claude/akms/nodes/`` raises ``RuntimeError``. The test
        passes if compile completes successfully — i.e. the implementation
        never attempts a vault write. The "fails compile if a write IS
        attempted" half is enforced by the guard; this case proves the
        attempt never happens.
        """
        fake_home = tmp_path / "fake_home"
        fake_home.mkdir(exist_ok=True)
        monkeypatch.setenv("HOME", str(fake_home))
        monkeypatch.delenv("AKMS_GLOBAL_VAULT", raising=False)

        vault_prefix = (fake_home / ".claude" / "akms" / "nodes").resolve()

        def _is_vault_target(target: Path) -> bool:
            try:
                resolved = target.resolve()
            except (OSError, RuntimeError):
                return False
            try:
                resolved.relative_to(vault_prefix)
            except ValueError:
                return False
            return True

        real_write_text = Path.write_text
        real_write_bytes = Path.write_bytes
        real_open = Path.open

        def _guarded_write_text(self, *args, **kwargs):
            if _is_vault_target(self):
                raise RuntimeError(
                    f"global vault write attempt (write_text) at {self!s}"
                )
            return real_write_text(self, *args, **kwargs)

        def _guarded_write_bytes(self, *args, **kwargs):
            if _is_vault_target(self):
                raise RuntimeError(
                    f"global vault write attempt (write_bytes) at {self!s}"
                )
            return real_write_bytes(self, *args, **kwargs)

        def _guarded_open(self, mode="r", *args, **kwargs):
            if any(flag in mode for flag in ("w", "a", "x", "+")) and _is_vault_target(
                self
            ):
                raise RuntimeError(
                    f"global vault write attempt (open mode={mode!r}) at {self!s}"
                )
            return real_open(self, mode, *args, **kwargs)

        monkeypatch.setattr(Path, "write_text", _guarded_write_text)
        monkeypatch.setattr(Path, "write_bytes", _guarded_write_bytes)
        monkeypatch.setattr(Path, "open", _guarded_open)

        # Compile must NOT raise — the guard would trip only if compile
        # attempted a vault write, which the read-only invariant forbids.
        out_dir = tmp_path / "out"
        result = compile_learning_source(
            request=make_request(),
            graph_slice=fixture_graph(),
            output_dir=out_dir,
        )
        assert result.packet_path is not None
        assert result.packet_path.exists()

    @pytest.mark.integration
    def test_global_vault_env_override_respected(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, make_request
    ) -> None:
        """``AKMS_GLOBAL_VAULT`` override is also never written to."""
        custom_vault = tmp_path / "custom_vault"
        # Intentionally do NOT mkdir; we want to assert it stays empty/absent.
        monkeypatch.setenv("AKMS_GLOBAL_VAULT", str(custom_vault))

        out_dir = tmp_path / "out"
        result = compile_learning_source(
            request=make_request(),
            graph_slice=fixture_graph(),
            output_dir=out_dir,
        )
        assert result.packet_path is not None
        assert result.packet_path.exists()

        offenders = _vault_files(custom_vault)
        assert offenders == [], (
            f"compile_learning_source wrote {len(offenders)} files under the "
            f"AKMS_GLOBAL_VAULT override: {offenders!r}"
        )

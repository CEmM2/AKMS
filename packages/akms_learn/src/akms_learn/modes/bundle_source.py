"""Mode 12 — Learning Source Bundle orchestrator.

Mode 12 (the *bundle source* mode) is the cross-mode aggregator that ensures
the seven-artifact bundle is produced for a given
:class:`LearningSourcePacket`. The orchestration is a thin
delegate to :func:`akms_learn.exporters.bundle.export`; future work may
expand this module to coordinate multiple mode outputs (e.g. interleaving
outline + anthology renderings) before bundling.

Like every Phase 4 mode, this module performs **no** I/O of its own beyond
forwarding to the bundle exporter — the exporter owns all disk writes, so
keeping the mode module a one-line passthrough preserves the
mode-vs-exporter separation declared in the Phase 4 context summary.
"""

from __future__ import annotations

from pathlib import Path
from typing import TYPE_CHECKING

from akms_learn.exporters import bundle as _bundle_exporter

if TYPE_CHECKING:
    from akms_learn.models import LearningSourcePacket

__all__ = ["bundle_source_mode"]


def bundle_source_mode(
    packet: "LearningSourcePacket",
    output_dir: str | Path,
) -> list[Path]:
    """Drive Mode 12 bundle assembly for *packet* into *output_dir*.

    Parameters
    ----------
    packet:
        The fully-validated :class:`LearningSourcePacket` produced by
        :func:`~akms_learn.compiler.compile_learning_source`.
    output_dir:
        Filesystem directory that will receive the seven-artifact bundle.
        Created on demand by the bundle exporter.

    Returns
    -------
    list[Path]
        Sorted absolute paths to every artifact written by the bundle
        exporter (the seven named files plus the two ``.gitkeep`` sentinels).
    """
    return _bundle_exporter.export(packet, Path(output_dir))

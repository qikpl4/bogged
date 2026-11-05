"""Orchestrate building the binary mapping output, one directory per version."""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path

from binfmt.layout import INDEX_FILE
from binfmt.writer import write_version
from builder.collect import collect_version_records

logger = logging.getLogger(__name__)

MANIFEST_FILE = "versions.json"


def _version_sort_key(name: str) -> list[tuple[int, int | str]]:
    # Compare digit runs numerically, so 1.21.5 sorts before 1.21.11.
    return [(0, int(part)) if part.isdigit() else (1, part) for part in re.split(r"(\d+)", name) if part]


def write_manifest(output_dir: Path) -> None:
    versions = sorted(
        (path.name for path in output_dir.iterdir() if (path / INDEX_FILE.format("mojmap")).is_file()),
        key=_version_sort_key,
    )
    (output_dir / MANIFEST_FILE).write_text(json.dumps(versions, indent=2) + "\n", encoding="utf-8")


def build_binary(
    output_dir: Path,
    sides: frozenset[str],
    intermediary_repo: Path | None,
    yarn_repo: Path | None,
    mojmap_dir: Path | None,
    versions: list[str],
) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        raise NotADirectoryError(f"output path is a file: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    for version in versions:
        records = collect_version_records(sides, intermediary_repo, yarn_repo, mojmap_dir, version)
        write_version(records, sides, output_dir / version)
    write_manifest(output_dir)
    logger.info("Wrote binary output to %s", output_dir)

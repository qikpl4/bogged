"""Orchestrate building the binary mapping output, one directory per version."""

from __future__ import annotations

import json
import logging
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

# Worker processes (on start methods other than fork) re-import this module, so make
# the sibling packages importable even without the path setup done by the entry point.
_HERE = str(Path(__file__).resolve().parent)
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

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


def _build_version(
    output_dir: Path,
    sides: frozenset[str],
    intermediary_repo: Path | None,
    yarn_repo: Path | None,
    mojmap_dir: Path | None,
    version: str,
) -> None:
    # Each version works entirely on its own files and directories, so versions
    # can be built concurrently without sharing state.
    # Must stay importable and picklable: it runs in worker processes.
    records = collect_version_records(sides, intermediary_repo, yarn_repo, mojmap_dir, version)
    write_version(records, sides, output_dir / version)


def build_binary(
    output_dir: Path,
    sides: frozenset[str],
    intermediary_repo: Path | None,
    yarn_repo: Path | None,
    mojmap_dir: Path | None,
    versions: list[str],
    jobs: int | None = None,
) -> None:
    if output_dir.exists() and not output_dir.is_dir():
        raise NotADirectoryError(f"output path is a file: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)

    workers = jobs if jobs is not None else (os.cpu_count() or 1)
    failures: dict[str, Exception] = {}
    with ProcessPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(_build_version, output_dir, sides, intermediary_repo, yarn_repo, mojmap_dir, version): version
            for version in versions
        }
        for future in as_completed(futures):
            version = futures[future]
            try:
                future.result()
            except Exception as error:  # Keep building the remaining versions, then report.
                logger.exception("%s: failed to build version", version)
                failures[version] = error

    if failures:
        names = ", ".join(sorted(failures))
        raise RuntimeError(f"failed to build {len(failures)} version(s): {names}")

    write_manifest(output_dir)
    logger.info("Wrote binary output to %s", output_dir)

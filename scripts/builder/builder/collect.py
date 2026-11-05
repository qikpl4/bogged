"""Collect all mapping records for a single Minecraft version."""

from __future__ import annotations

import logging
from pathlib import Path

from parsers.proguard import parse_proguard
from parsers.tiny import parse_tiny
from parsers.yarn import parse_yarn_repository

from .attach_mojmap import attach_mojmap
from .attach_yarn import attach_yarn
from .seed_intermediary import seed_intermediary_records

logger = logging.getLogger(__name__)


def restrict_to_sides(records: list[dict], sides: frozenset[str]) -> list[dict]:
    """Drop side entries that were not requested, and records left with no sides."""
    kept: list[dict] = []
    for record in records:
        record["sides"] = {side: entry for side, entry in record["sides"].items() if side in sides}
        if record["sides"]:
            kept.append(record)
    return kept


def collect_version_records(
    sides: frozenset[str],
    intermediary_repo: Path | None,
    yarn_repo: Path | None,
    mojmap_dir: Path | None,
    version: str,
) -> list[dict]:
    use_mojmap = "mojmap" in sides
    use_yarn = "yarn" in sides
    # Yarn names can only be linked to records through intermediary, so intermediary
    # is loaded whenever yarn is requested, even if its own side is not emitted.
    use_intermediary = "intermediary" in sides or use_yarn

    logger.info("Processing %s", version)

    mojmap = None
    if use_mojmap:
        mojmap_path = mojmap_dir / f"{version}.txt"
        mojmap = parse_proguard(mojmap_path) if mojmap_path.is_file() else None
        if mojmap is None:
            logger.warning("%s: missing mojmap mappings at %s", version, mojmap_path)

    intermediary = None
    if use_intermediary:
        intermediary_path = intermediary_repo / "mappings" / f"{version}.tiny"
        try:
            intermediary = parse_tiny(intermediary_path) if intermediary_path.is_file() else None
        except Exception as error:
            logger.error("%s: failed to parse intermediary mappings: %s", version, error)
            raise
        if intermediary is None:
            logger.warning("%s: missing intermediary mappings at %s", version, intermediary_path)

    yarn = None
    if use_yarn:
        try:
            yarn = parse_yarn_repository(yarn_repo, version)
        except Exception as error:
            logger.warning("%s: missing or unreadable yarn mappings: %s", version, error)
            yarn = None

    intermediary_to_official = None
    if intermediary is not None:
        intermediary_to_official = {}
        for entry in intermediary.classes:
            intermediary_to_official.setdefault(entry.mapped_name, entry.name)

    records, class_by_official, member_by_official, class_by_intermediary, member_by_intermediary = \
        seed_intermediary_records(intermediary)

    attach_mojmap(records, mojmap, class_by_official, member_by_official)
    attach_yarn(records, yarn, intermediary_to_official, class_by_intermediary, member_by_intermediary)
    return restrict_to_sides(records, sides)

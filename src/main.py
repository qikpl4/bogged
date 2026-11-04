#!/usr/bin/env python3
"""Generate a SQLite database containing Minecraft mapping relationships."""

from __future__ import annotations

import argparse
import logging
import os
import sqlite3
import subprocess
import sys
import tempfile
import uuid
from datetime import datetime, timezone
from pathlib import Path
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parent))

from parsers.proguard import ProGuardMapping, parse_proguard  # noqa: E402
from parsers.tiny import TinyMapping, parse_tiny  # noqa: E402
from parsers.yarn import YarnMapping, parse_yarn_repository  # noqa: E402
from parsers.descriptor import normalize_jvm_descriptor  # noqa: E402

logger = logging.getLogger(__name__)

SIDES = ("mojmap", "yarn", "intermediary")
KINDS = ("class", "field", "method")
SCHEMA_VERSION = "1"

SCHEMA = """
CREATE TABLE meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE versions (
    version TEXT PRIMARY KEY,
    generated_at TEXT NOT NULL,
    class_count INTEGER NOT NULL,
    field_count INTEGER NOT NULL,
    method_count INTEGER NOT NULL
);

CREATE TABLE mappings (
    mapping_id INTEGER PRIMARY KEY,
    version TEXT NOT NULL REFERENCES versions(version) ON DELETE CASCADE,
    kind TEXT NOT NULL CHECK (kind IN ('class', 'field', 'method')),
    descriptor TEXT,
    CHECK (
        (kind = 'class' AND descriptor IS NULL)
        OR (kind IN ('field', 'method') AND descriptor IS NOT NULL)
    )
);

CREATE TABLE mapping_entries (
    mapping_id INTEGER NOT NULL REFERENCES mappings(mapping_id) ON DELETE CASCADE,
    side TEXT NOT NULL CHECK (side IN ('mojmap', 'yarn', 'intermediary')),
    name TEXT NOT NULL,
    class TEXT NOT NULL,
    PRIMARY KEY (mapping_id, side)
);

CREATE INDEX idx_mappings_version_kind_descriptor
    ON mappings(version, kind, descriptor, mapping_id);

CREATE INDEX idx_mapping_entries_side_name_class
    ON mapping_entries(side, name, class, mapping_id);

CREATE INDEX idx_mapping_entries_side_class_name
    ON mapping_entries(side, class, name, mapping_id);
"""


def path_from_java_name(name: str) -> str:
    return name.replace(".", "/")


def simple_name(path: str) -> str:
    base = path.rsplit("/", 1)[-1]
    return base.rsplit("$", 1)[-1] if "$" in base else base


def side_entry(class_path: str, name: str) -> dict[str, str]:
    return {"name": name, "class": class_path}


def new_record(kind: str, descriptor: str | None) -> dict:
    return {"kind": kind, "descriptor": descriptor, "sides": {}}


def resolve_official_from_intermediary(intermediary_to_official: dict[str, str], name: str) -> str:
    return intermediary_to_official.get(name, name)


def official_descriptor(
    descriptor: str,
    intermediary_to_official: dict[str, str] | None,
) -> str:
    if intermediary_to_official is None:
        return descriptor
    try:
        return normalize_jvm_descriptor(descriptor, lambda name: resolve_official_from_intermediary(intermediary_to_official, name))
    except ValueError:
        return descriptor


def seed_intermediary_records(
    tiny: TinyMapping | None,
) -> tuple[
    list[dict],
    dict[str, dict],
    dict[tuple[str, str, str, str], dict],
    dict[str, dict],
    dict[tuple[str, str, str, str], dict],
]:
    records: list[dict] = []
    class_by_official: dict[str, dict] = {}
    class_by_intermediary: dict[str, dict] = {}
    member_by_official: dict[tuple[str, str, str, str], dict] = {}
    member_by_intermediary: dict[tuple[str, str, str, str], dict] = {}

    if tiny is None:
        return records, class_by_official, member_by_official, class_by_intermediary, member_by_intermediary

    intermediary_class_paths = {entry.name: entry.mapped_name for entry in tiny.classes}

    for entry in tiny.classes:
        record = new_record("class", None)
        class_path = entry.mapped_name
        record["sides"]["intermediary"] = side_entry(class_path, simple_name(class_path))
        records.append(record)
        class_by_official.setdefault(entry.name, record)
        class_by_intermediary.setdefault(class_path, record)

    for entry in tiny.members:
        record = new_record(entry.kind, entry.descriptor)
        owner_path = intermediary_class_paths.get(entry.owner, entry.owner)
        record["sides"]["intermediary"] = side_entry(owner_path, entry.mapped_name)
        records.append(record)
        official_key = (entry.kind, entry.owner, entry.descriptor, entry.name)
        intermediary_key = (entry.kind, entry.owner, entry.descriptor, entry.mapped_name)
        if official_key in member_by_official:
            raise ValueError(f"duplicate intermediary mapping for {official_key}")
        member_by_official[official_key] = record
        member_by_intermediary[intermediary_key] = record

    return records, class_by_official, member_by_official, class_by_intermediary, member_by_intermediary


def attach_mojmap(
    records: list[dict],
    mapping: ProGuardMapping | None,
    class_by_official: dict[str, dict],
    member_by_official: dict[tuple[str, str, str, str], dict],
) -> None:
    if mapping is None:
        return
    for entry in mapping.classes:
        class_path = path_from_java_name(entry.name)
        side = side_entry(class_path, simple_name(class_path))
        record = class_by_official.get(entry.target)
        if record is not None:
            record["sides"]["mojmap"] = side
        else:
            record = new_record("class", None)
            record["sides"]["mojmap"] = side
            records.append(record)
            class_by_official[entry.target] = record

    mojmap_owner_paths = {entry.target: path_from_java_name(entry.name) for entry in mapping.classes}

    for entry in mapping.members:
        owner_path = mojmap_owner_paths.get(entry.owner, entry.owner)
        side = side_entry(owner_path, entry.mapped_name)
        key = (entry.kind, entry.owner, entry.descriptor, entry.name)
        record = member_by_official.get(key)
        if record is not None:
            record["sides"]["mojmap"] = side
        else:
            record = new_record(entry.kind, entry.descriptor)
            record["sides"]["mojmap"] = side
            records.append(record)
            member_by_official[key] = record


def attach_yarn(
    records: list[dict],
    mapping: YarnMapping | None,
    intermediary_to_official: dict[str, str] | None,
    class_by_intermediary: dict[str, dict],
    member_by_intermediary: dict[tuple[str, str, str, str], dict],
) -> None:
    if mapping is None:
        return

    def official_owner(owner: str) -> str:
        if intermediary_to_official is None:
            return owner
        return intermediary_to_official.get(owner, owner)

    for entry in mapping.classes:
        if entry.mapped_name is None:
            continue
        side = side_entry(entry.mapped_name, simple_name(entry.mapped_name))
        record = class_by_intermediary.get(entry.name)
        if record is not None:
            record["sides"]["yarn"] = side
        else:
            record = new_record("class", None)
            record["sides"]["yarn"] = side
            records.append(record)
            class_by_intermediary[entry.name] = record
            logger.debug("yarn class %s did not match an intermediary class", entry.name)

    for entry in mapping.members:
        if entry.mapped_name is None or entry.owner_mapped is None:
            continue
        descriptor = official_descriptor(entry.descriptor, intermediary_to_official)
        owner = official_owner(entry.owner)
        side = side_entry(entry.owner_mapped, entry.mapped_name)
        key = (entry.kind, owner, descriptor, entry.name)
        record = member_by_intermediary.get(key)
        if record is not None:
            record["sides"]["yarn"] = side
        else:
            record = new_record(entry.kind, descriptor)
            record["sides"]["yarn"] = side
            records.append(record)
            member_by_intermediary[key] = record


def collect_version_records(intermediary_repo: Path, yarn_repo: Path, mojmap_dir: Path, version: str) -> list[dict]:
    mojmap_path = mojmap_dir / f"{version}.txt"
    intermediary_path = intermediary_repo / "mappings" / f"{version}.tiny"

    logger.info("Processing %s", version)
    mojmap = parse_proguard(mojmap_path) if mojmap_path.is_file() else None
    if mojmap is None:
        logger.warning("%s: missing mojmap mappings at %s", version, mojmap_path)

    try:
        intermediary = parse_tiny(intermediary_path) if intermediary_path.is_file() else None
    except Exception as error:
        logger.error("%s: failed to parse intermediary mappings: %s", version, error)
        raise
    if intermediary is None:
        logger.warning("%s: missing intermediary mappings at %s", version, intermediary_path)

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
    return records


def insert_version(connection: sqlite3.Connection, version: str, records: list[dict], generated_at: str) -> None:
    counts = Counter(record["kind"] for record in records)
    connection.execute(
        """
        INSERT INTO versions(version, generated_at, class_count, field_count, method_count)
        VALUES (?, ?, ?, ?, ?)
        """,
        (version, generated_at, counts["class"], counts["field"], counts["method"]),
    )

    for record in records:
        cursor = connection.execute(
            "INSERT INTO mappings(version, kind, descriptor) VALUES (?, ?, ?)",
            (version, record["kind"], record["descriptor"]),
        )
        mapping_id = cursor.lastrowid
        connection.executemany(
            "INSERT INTO mapping_entries(mapping_id, side, name, class) VALUES (?, ?, ?, ?)",
            [
                (mapping_id, side, entry["name"], entry["class"])
                for side, entry in record["sides"].items()
            ],
        )

    logger.info(
        "%s: staged %d records (%d classes, %d fields, %d methods)",
        version,
        len(records),
        counts["class"],
        counts["field"],
        counts["method"],
    )


def create_database(
    output_path: Path,
    intermediary_repo: Path,
    yarn_repo: Path,
    mojmap_dir: Path,
    versions: list[str],
) -> None:
    if output_path.exists() and output_path.is_dir():
        raise IsADirectoryError(f"output path is a directory: {output_path}")

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = output_path.parent / f".{output_path.name}.tmp-{os.getpid()}-{uuid.uuid4().hex}"

    generated_at = datetime.now(timezone.utc).isoformat()
    try:
        connection = sqlite3.connect(temporary_path)
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            connection.execute("PRAGMA journal_mode = MEMORY")
            connection.execute("PRAGMA synchronous = OFF")
            connection.execute("PRAGMA temp_store = MEMORY")
            connection.executescript(SCHEMA)
            connection.execute("BEGIN")
            for index, version in enumerate(versions):
                records = collect_version_records(intermediary_repo, yarn_repo, mojmap_dir, version)
                insert_version(connection, version, records, generated_at)
            connection.executemany(
                "INSERT INTO meta(key, value) VALUES (?, ?)",
                [
                    ("app", "minecraft-mappings"),
                    ("schema_version", SCHEMA_VERSION),
                    ("generated_at", generated_at),
                ],
            )
            connection.commit()
            connection.execute("VACUUM")
            check = connection.execute("PRAGMA quick_check").fetchone()
            if check is None or check[0] != "ok":
                raise sqlite3.DatabaseError(f"SQLite integrity check failed: {check!r}")
        finally:
            connection.close()
        os.replace(temporary_path, output_path)
    except BaseException:
        try:
            temporary_path.unlink(missing_ok=True)
        finally:
            raise


def parse_versions(values: list[str] | None) -> list[str] | None:
    if values is None:
        return None
    versions: list[str] = []
    seen: set[str] = set()
    for value in values:
        for version in value.split(","):
            version = version.strip()
            if not version:
                continue
            if version in (".", "..") or "/" in version or "\\" in version:
                raise ValueError(f"unsafe version name: {version!r}")
            if version not in seen:
                seen.add(version)
                versions.append(version)
    return versions


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True, help="Path to the SQLite file to write")
    parser.add_argument("--intermediary-repo", type=Path, required=True, help="Path to a cloned FabricMC/intermediary repository")
    parser.add_argument("--yarn-repo", type=Path, required=True, help="Path to a cloned FabricMC/yarn repository with local refs fetched")
    parser.add_argument("--mojmap-dir", type=Path, required=True, help="Directory containing <version>.txt Mojang mappings")
    parser.add_argument(
        "--versions",
        nargs="+",
        default=None,
        help="Only process these versions, e.g. --versions 1.21.11 1.20.6. Comma-separated values are also accepted.",
    )
    return parser.parse_args()


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
    args = parse_args()

    if not args.intermediary_repo.is_dir():
        raise FileNotFoundError(f"intermediary repository not found: {args.intermediary_repo}")
    if not args.yarn_repo.is_dir():
        raise FileNotFoundError(f"yarn repository not found: {args.yarn_repo}")
    if not args.mojmap_dir.is_dir():
        raise FileNotFoundError(f"mojmap directory not found: {args.mojmap_dir}")

    git_check = subprocess.run(
        ["git", "-C", str(args.yarn_repo), "rev-parse", "--is-inside-work-tree"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if git_check.returncode != 0:
        raise ValueError(f"yarn repository is not a git repository: {args.yarn_repo}")

    try:
        requested_versions = parse_versions(args.versions)
    except ValueError as error:
        logger.error("%s", error)
        return 2

    if requested_versions is None:
        version_files = sorted(path for path in args.mojmap_dir.glob("*.txt") if path.is_file())
        if not version_files:
            logger.warning("no mojmap .txt files found in %s", args.mojmap_dir)
            return 0
        versions = [version_file.stem for version_file in version_files]
    else:
        versions = requested_versions

    create_database(args.output, args.intermediary_repo, args.yarn_repo, args.mojmap_dir, versions)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

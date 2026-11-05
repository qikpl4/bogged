"""Attach Yarn names to mapping records."""

from __future__ import annotations

import logging

from parsers.yarn import YarnMapping

from .naming import new_record, official_descriptor, side_entry, simple_name

logger = logging.getLogger(__name__)


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

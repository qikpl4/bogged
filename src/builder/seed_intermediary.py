"""Seed mapping records from the FabricMC intermediary (tiny) mappings."""

from __future__ import annotations

from parsers.tiny import TinyMapping

from .naming import new_record, side_entry, simple_name


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

"""Attach Mojang (mojmap) names to mapping records."""

from __future__ import annotations

from parsers.proguard import ProGuardMapping

from .naming import new_record, path_from_java_name, side_entry, simple_name


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

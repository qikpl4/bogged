"""Naming and descriptor helpers shared by the mapping builder stages."""

from __future__ import annotations

from parsers.descriptor import normalize_jvm_descriptor


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

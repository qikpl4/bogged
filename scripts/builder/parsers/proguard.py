"""Parser for Mojang's ProGuard/client mappings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import re

from .descriptor import DescriptorError, field_descriptor, method_descriptor

logger = logging.getLogger(__name__)

ClassLine = re.compile(r"^(?P<source>[^\s:][^:]*) -> (?P<target>[^:]+):$")
MemberPrefix = re.compile(r"^\s+(?:\d+:\d+:)?")
FieldMember = re.compile(
    r"^\s+(?:\d+:\d+:)?(?P<type>[^\s()]+)\s+(?P<name>[^\s()]+)\s+->\s+(?P<target>\S+)$"
)
MethodMember = re.compile(
    r"^\s+(?:\d+:\d+:)?(?P<return>[^\s()]+)\s+(?P<name>[^\s()]+)\((?P<args>[^)]*)\)\s+->\s+(?P<target>\S+)$"
)


class ProGuardParseError(ValueError):
    """Raised when a ProGuard mapping file cannot be parsed."""


@dataclass(frozen=True)
class ClassEntry:
    name: str
    """Mapped (mojmap) fully qualified class name, using dots."""
    target: str
    """Official/obfuscated class name."""


@dataclass(frozen=True)
class MemberEntry:
    kind: str
    """'field' or 'method'."""
    owner: str
    """Official/obfuscated owning class name."""
    name: str
    """Official/obfuscated member name."""
    mapped_name: str
    """Mapped (mojmap) member name."""
    descriptor: str
    """JVM descriptor with official class names where possible."""


@dataclass(frozen=True)
class ProGuardMapping:
    classes: tuple[ClassEntry, ...]
    members: tuple[MemberEntry, ...]


@dataclass(frozen=True)
class _RawMember:
    kind: str
    owner: str
    name: str
    mapped_name: str
    return_type: str | None
    argument_types: tuple[str, ...]
    field_type: str | None


def _read_class_entries(path: Path) -> list[ClassEntry]:
    classes: list[ClassEntry] = []
    with path.open("r", encoding="utf-8") as mapping_file:
        for line_number, line in enumerate(mapping_file, start=1):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if line[0] in " \t":
                continue
            match = ClassLine.fullmatch(line)
            if not match:
                raise ProGuardParseError(f"{path}:{line_number}: unrecognized class mapping {line!r}")
            classes.append(ClassEntry(match.group("source"), match.group("target").replace(".", "/")))
    return classes


def _split_arguments(arguments: str) -> list[str]:
    if not arguments.strip():
        return []
    return [argument.strip() for argument in arguments.split(",") if argument.strip()]


def _read_raw_members(path: Path, classes: list[ClassEntry]) -> list[_RawMember]:
    members: list[_RawMember] = []
    current_class: ClassEntry | None = None
    class_by_target = {entry.target: entry for entry in classes}

    with path.open("r", encoding="utf-8") as mapping_file:
        for line_number, line in enumerate(mapping_file, start=1):
            line = line.rstrip("\n")
            if not line or line.startswith("#"):
                continue
            if line[0] not in " \t":
                match = ClassLine.fullmatch(line)
                if not match:
                    raise ProGuardParseError(f"{path}:{line_number}: unrecognized class mapping {line!r}")
                raw_target = match.group("target").replace(".", "/")
                current_class = class_by_target[raw_target]
                continue
            if current_class is None:
                raise ProGuardParseError(f"{path}:{line_number}: member mapping before any class")

            method = MethodMember.fullmatch(line)
            if method:
                members.append(
                    _RawMember(
                        kind="method",
                        owner=current_class.target,
                        name=method.group("target"),
                        mapped_name=method.group("name"),
                        return_type=method.group("return"),
                        argument_types=tuple(_split_arguments(method.group("args"))),
                        field_type=None,
                    )
                )
                continue

            field = FieldMember.fullmatch(line)
            if field:
                members.append(
                    _RawMember(
                        kind="field",
                        owner=current_class.target,
                        name=field.group("target"),
                        mapped_name=field.group("name"),
                        return_type=None,
                        argument_types=(),
                        field_type=field.group("type"),
                    )
                )
                continue

            raise ProGuardParseError(f"{path}:{line_number}: unrecognized member mapping {line!r}")

    return members


def parse_proguard(path: str | Path) -> ProGuardMapping:
    mapping_path = Path(path)
    try:
        classes = _read_class_entries(mapping_path)
        reverse = {entry.name: entry.target for entry in classes}

        def resolve(java_class: str) -> str:
            mapped = reverse.get(java_class)
            if mapped is not None:
                return mapped
            # Classes absent from the mappings are external libraries. ProGuard
            # uses dotted names; JVM descriptors use slash-separated names.
            return java_class.replace(".", "/")

        raw_members = _read_raw_members(mapping_path, classes)
        members: list[MemberEntry] = []
        for raw in raw_members:
            try:
                if raw.kind == "method":
                    descriptor = method_descriptor(raw.return_type or "void", list(raw.argument_types), resolve)
                else:
                    descriptor = field_descriptor(raw.field_type or "", resolve)
            except DescriptorError as error:
                raise ProGuardParseError(f"{mapping_path}: invalid descriptor for {raw.owner}.{raw.name}: {error}") from error
            members.append(
                MemberEntry(
                    kind=raw.kind,
                    owner=raw.owner,
                    name=raw.name,
                    mapped_name=raw.mapped_name,
                    descriptor=descriptor,
                )
            )
        logger.debug("%s: parsed %d classes and %d members", mapping_path, len(classes), len(members))
        return ProGuardMapping(classes=tuple(classes), members=tuple(members))
    except UnicodeDecodeError as error:
        raise ProGuardParseError(f"{mapping_path}: not a UTF-8 ProGuard mapping file") from error

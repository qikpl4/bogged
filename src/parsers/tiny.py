"""Parser for FabricMC intermediary tiny v1 mappings."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging

from .descriptor import DescriptorError, normalize_jvm_descriptor

logger = logging.getLogger(__name__)


class TinyParseError(ValueError):
    """Raised when a tiny mapping file cannot be parsed."""


@dataclass(frozen=True)
class ClassEntry:
    name: str
    """Official/obfuscated class name."""
    mapped_name: str
    """Intermediary class name, using slash-separated package segments."""


@dataclass(frozen=True)
class MemberEntry:
    kind: str
    """'field' or 'method'."""
    owner: str
    """Official/obfuscated owning class name."""
    name: str
    """Official/obfuscated member name."""
    mapped_name: str
    """Intermediary member name."""
    descriptor: str
    """JVM descriptor (official class names are already used)."""


@dataclass(frozen=True)
class TinyMapping:
    classes: tuple[ClassEntry, ...]
    members: tuple[MemberEntry, ...]


def _identity(name: str) -> str:
    return name


def parse_tiny(path: str | Path) -> TinyMapping:
    tiny_path = Path(path)
    classes: list[ClassEntry] = []
    members: list[MemberEntry] = []

    try:
        with tiny_path.open("r", encoding="utf-8") as mapping_file:
            first = mapping_file.readline().rstrip("\n")
            parts = first.split("\t")
            if len(parts) < 3 or parts[0] != "v1":
                raise TinyParseError(f"{tiny_path}: expected a v1 tiny header, got {first!r}")

            for line_number, line in enumerate(mapping_file, start=2):
                line = line.rstrip("\n")
                if not line or line.startswith("#"):
                    continue
                parts = line.split("\t")
                directive = parts[0]
                try:
                    if directive == "CLASS" and len(parts) == 3:
                        classes.append(ClassEntry(parts[1], parts[2]))
                        continue
                    if directive in ("FIELD", "METHOD") and len(parts) == 5:
                        kind = "field" if directive == "FIELD" else "method"
                        descriptor = normalize_jvm_descriptor(parts[2], _identity)
                        members.append(
                            MemberEntry(
                                kind=kind,
                                owner=parts[1],
                                name=parts[3],
                                mapped_name=parts[4],
                                descriptor=descriptor,
                            )
                        )
                        continue
                except DescriptorError as error:
                    raise TinyParseError(f"{tiny_path}:{line_number}: {error}") from error
                raise TinyParseError(f"{tiny_path}:{line_number}: unrecognized tiny mapping {line!r}")
    except UnicodeDecodeError as error:
        raise TinyParseError(f"{tiny_path}: not a UTF-8 tiny mapping file") from error

    logger.debug("%s: parsed %d classes and %d members", tiny_path, len(classes), len(members))
    return TinyMapping(classes=tuple(classes), members=tuple(members))

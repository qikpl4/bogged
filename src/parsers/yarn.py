"""Parser for FabricMC yarn .mapping files stored in a git repository."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import logging
import subprocess
import tarfile

from .descriptor import DescriptorError, normalize_jvm_descriptor

logger = logging.getLogger(__name__)


class YarnParseError(ValueError):
    """Raised when yarn mappings cannot be read."""


@dataclass(frozen=True)
class ClassEntry:
    name: str
    """Official/intermediary class name (full, slash-separated)."""
    mapped_name: str | None
    """Yarn class name, or None when the class has no yarn name."""
    source_simple: str
    mapped_simple: str | None


@dataclass(frozen=True)
class MemberEntry:
    kind: str
    """'field' or 'method'."""
    owner: str
    """Official/intermediary owning class name (full, slash-separated)."""
    owner_mapped: str | None
    """Yarn owning class name, or None when unavailable."""
    name: str
    """Official/intermediary member name."""
    mapped_name: str | None
    """Yarn member name, or None when the member has no yarn name."""
    descriptor: str
    """JVM descriptor using intermediary class names."""


@dataclass(frozen=True)
class YarnMapping:
    classes: tuple[ClassEntry, ...]
    members: tuple[MemberEntry, ...]
    ref: str


@dataclass
class _ClassFrame:
    source_full: str
    target_full: str | None
    source_simple: str
    target_simple: str | None


def _identity(name: str) -> str:
    return name


def _depth(line: str) -> int:
    return len(line) - len(line.lstrip("\t"))


def _joined(parent: str, simple: str) -> str:
    return f"{parent}${simple}" if parent else simple


def parse_yarn_text(text: str, origin: str = "<yarn>") -> tuple[list[ClassEntry], list[MemberEntry]]:
    classes: list[ClassEntry] = []
    members: list[MemberEntry] = []
    stack: list[_ClassFrame] = []

    for line_number, raw_line in enumerate(text.splitlines(), start=1):
        line = raw_line.rstrip("\n")
        if not line or not line.strip():
            continue
        depth = _depth(line)
        stripped = line.lstrip("\t")
        parts = stripped.split()
        directive = parts[0]
        if directive in ("COMMENT", "ARG"):
            continue

        if directive == "CLASS":
            if len(parts) not in (2, 3):
                raise YarnParseError(f"{origin}:{line_number}: invalid CLASS mapping {stripped!r}")
            source_simple = parts[1]
            target_simple = parts[2] if len(parts) == 3 else None
            if target_simple is None and source_simple.isdigit():
                # Anonymous synthetic classes keep their numeric suffix in the mapped jar.
                target_simple = source_simple
            parent = stack[depth - 1] if depth else None
            if depth and parent is None:
                raise YarnParseError(f"{origin}:{line_number}: nested class without a parent")
            source_full = _joined(parent.source_full if parent else "", source_simple)
            if target_simple is None:
                target_full = None
            elif parent is None:
                target_full = target_simple
            elif parent.target_full is None:
                target_full = None
            else:
                target_full = _joined(parent.target_full, target_simple)
            frame = _ClassFrame(source_full, target_full, source_simple, target_simple)
            del stack[depth:]
            stack.append(frame)
            classes.append(ClassEntry(source_full, target_full, source_simple, target_simple))
            continue

        if directive in ("FIELD", "METHOD"):
            if depth == 0:
                raise YarnParseError(f"{origin}:{line_number}: member mapping outside of any class")
            if depth > len(stack):
                raise YarnParseError(f"{origin}:{line_number}: member mapping without an owning class")
            owner = stack[depth - 1]
            if len(parts) == 4:
                name, mapped_name, descriptor = parts[1], parts[2], parts[3]
            elif len(parts) == 3:
                name, mapped_name, descriptor = parts[1], None, parts[2]
            else:
                raise YarnParseError(f"{origin}:{line_number}: invalid {directive} mapping {stripped!r}")
            try:
                normalized = normalize_jvm_descriptor(descriptor, _identity)
            except DescriptorError as error:
                raise YarnParseError(f"{origin}:{line_number}: {error}") from error
            members.append(
                MemberEntry(
                    kind="field" if directive == "FIELD" else "method",
                    owner=owner.source_full,
                    owner_mapped=owner.target_full,
                    name=name,
                    mapped_name=mapped_name,
                    descriptor=normalized,
                )
            )
            continue

        raise YarnParseError(f"{origin}:{line_number}: unrecognized yarn mapping {stripped!r}")

    return classes, members


def yarn_ref_for_version(repository: str | Path, version: str) -> str | None:
    repo = Path(repository)
    for ref in (f"refs/heads/{version}", f"refs/tags/{version}"):
        result = subprocess.run(
            ["git", "-C", str(repo), "cat-file", "-e", f"{ref}^{{commit}}"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        if result.returncode == 0:
            return ref
    return None


def parse_yarn_repository(repository: str | Path, version: str) -> YarnMapping:
    repo = Path(repository)
    ref = yarn_ref_for_version(repo, version)
    if ref is None:
        raise YarnParseError(f"no branch or tag named {version!r} in {repo}")

    classes: list[ClassEntry] = []
    members: list[MemberEntry] = []
    process = subprocess.Popen(
        ["git", "-C", str(repo), "archive", ref, "mappings"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    assert process.stdout is not None
    try:
        with tarfile.open(fileobj=process.stdout, mode="r|") as archive:
            for member in archive:
                if not member.isfile() or not member.name.endswith(".mapping"):
                    continue
                extracted = archive.extractfile(member)
                if extracted is None:
                    continue
                data = extracted.read()
                text = data.decode("utf-8")
                parsed_classes, parsed_members = parse_yarn_text(text, origin=f"{ref}:{member.name}")
                classes.extend(parsed_classes)
                members.extend(parsed_members)
    finally:
        process.stdout.close()
    stderr = process.stderr.read().decode("utf-8", errors="replace") if process.stderr else ""
    returncode = process.wait()
    if returncode != 0:
        raise YarnParseError(f"git archive failed for {ref} in {repo}: {stderr.strip()}")

    return YarnMapping(classes=tuple(classes), members=tuple(members), ref=ref)

"""Write one version's records as one index per side plus batch files."""

from __future__ import annotations

import logging
import math
import random
import struct
from dataclasses import dataclass
from pathlib import Path

from .layout import (
    BATCH_COUNT,
    BATCH_FILE,
    END_OF_MATCHES,
    INDEX_FILE,
    KIND_CODES,
    MAX_FIELD_LENGTH,
    SHUFFLE_SEED,
    SIDE_ORDER,
    gzip_bytes,
    side_mask,
)

logger = logging.getLogger(__name__)

MAX_OFFSET = 0xFFFFFFFE


@dataclass(frozen=True)
class _Prepared:
    sides: tuple[tuple[bytes, bytes], ...]
    """(name, owner class) per requested side, in canonical order. Both empty when the side is absent."""
    descriptor: bytes
    kind: int


def _prepare(record: dict, ordered_sides: list[str]) -> _Prepared | None:
    sides = []
    for side in ordered_sides:
        entry = record["sides"].get(side)
        if entry is None:
            sides.append((b"", b""))
        else:
            sides.append((entry["name"].encode("utf-8"), entry["class"].encode("utf-8")))
    descriptor = (record["descriptor"] or "").encode("utf-8")
    fields = [field for pair in sides for field in pair] + [descriptor]
    if any(len(field) > MAX_FIELD_LENGTH for field in fields):
        return None
    return _Prepared(tuple(sides), descriptor, KIND_CODES[record["kind"]])


def _encode_record(prepared: _Prepared) -> bytes:
    out = bytearray()
    for name, owner in prepared.sides:
        out.append(len(name))
        out += name
        out.append(len(owner))
        out += owner
    out.append(len(prepared.descriptor))
    out += prepared.descriptor
    out.append(prepared.kind)
    return bytes(out)


def write_version(records: list[dict], sides: frozenset[str], version_dir: Path) -> None:
    ordered_sides = [side for side in SIDE_ORDER if side in sides]
    mask = side_mask(sides)

    prepared: list[_Prepared] = []
    skipped = 0
    for record in records:
        item = _prepare(record, ordered_sides)
        if item is None:
            skipped += 1
        else:
            prepared.append(item)
    if skipped:
        logger.warning(
            "%s: skipped %d records with a name or descriptor longer than %d bytes",
            version_dir.name,
            skipped,
            MAX_FIELD_LENGTH,
        )

    order = list(range(len(prepared)))
    random.Random(SHUFFLE_SEED).shuffle(order)
    per_batch = max(1, math.ceil(len(order) / BATCH_COUNT))
    batches = [order[chunk * per_batch:(chunk + 1) * per_batch] for chunk in range(BATCH_COUNT)]

    version_dir.mkdir(parents=True, exist_ok=True)

    # Index entries grouped by side. Each side's index only holds names from that side,
    # and a name can appear once per batch it has matches in.
    index_entries: dict[str, list[tuple[bytes, int, int]]] = {side: [] for side in SIDE_ORDER}
    for chunk, members in enumerate(batches):
        data = bytearray()
        offsets: dict[int, int] = {}
        for member in members:
            offsets[member] = len(data)
            data += _encode_record(prepared[member])

        matches: dict[tuple[int, bytes], list[int]] = {}
        for member in members:
            for position, (name, _owner) in enumerate(prepared[member].sides):
                if name:
                    matches.setdefault((position, name), []).append(offsets[member])

        for position, name in sorted(matches):
            start = len(data)
            if start > MAX_OFFSET:
                raise ValueError(f"{version_dir.name}: batch {chunk} is too large for 32-bit offsets")
            for offset in matches[(position, name)]:
                data += struct.pack("<I", offset)
            data += struct.pack("<I", END_OF_MATCHES)
            index_entries[ordered_sides[position]].append((name, chunk, start))

        (version_dir / BATCH_FILE.format(chunk)).write_bytes(gzip_bytes(bytes(data)))

    for side in SIDE_ORDER:
        index = bytearray(struct.pack("<H", mask))
        for name, chunk, start in sorted(index_entries[side]):
            index += struct.pack("<H", len(name) + 8)
            index.append(len(name))
            index += name
            index.append(chunk)
            index += struct.pack("<I", start)
        (version_dir / INDEX_FILE.format(side)).write_bytes(gzip_bytes(bytes(index)))

    logger.info(
        "%s: wrote %d records in %d batches with %d index entries",
        version_dir.name,
        len(prepared),
        sum(1 for members in batches if members),
        sum(len(entries) for entries in index_entries.values()),
    )

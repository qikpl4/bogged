"""Constants for the binary mapping format.

All integers are little-endian. Variable-length fields are a one-byte length
followed by the content, so no field may exceed MAX_FIELD_LENGTH bytes.

Every file is a standard gzip stream (RFC 1952), so it can be read with
zlib, Python's gzip module, or pako. Offsets refer to the decompressed bytes.
"""

from __future__ import annotations

import gzip

BATCH_COUNT = 16
"""Batch files per version. Fewer, larger batches compress better. Must stay within the one-byte chunk ID."""

SHUFFLE_SEED = 67
"""Seed for the deterministic shuffle that assigns records to batches."""

MAX_FIELD_LENGTH = 255
"""Largest value a one-byte length prefix can hold."""

END_OF_MATCHES = 0xFFFFFFFF
"""Terminator for a match list. Never a valid record offset."""

SIDE_BITS: dict[str, int] = {
    "mojmap": 1 << 0,
    "yarn": 1 << 1,
    "intermediary": 1 << 2,
}
"""Bit assigned to each side in the header bitmask. The format reserves room for eight sides."""

SIDE_ORDER: tuple[str, ...] = tuple(SIDE_BITS)
"""Sides in bit order. Record blocks list names in this order, skipping sides not present."""

INDEX_FILE = "index_{}.bin.gz"
"""One index per side, formatted with the side name."""
BATCH_FILE = "batch_{:03d}.bin.gz"

KIND_CODES = {"class": 0, "field": 1, "method": 2}


def side_mask(sides: frozenset[str] | set[str]) -> int:
    unknown = set(sides) - set(SIDE_BITS)
    if unknown:
        raise ValueError(f"no bit assigned for side(s): {', '.join(sorted(unknown))}")
    mask = 0
    for side in sides:
        mask |= SIDE_BITS[side]
    return mask


def gzip_bytes(data: bytes) -> bytes:
    # mtime=0 keeps the output byte-for-byte reproducible for the same input.
    return gzip.compress(data, mtime=0)

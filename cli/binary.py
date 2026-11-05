"""Binary format parsing for the packed mapping data.

Layout (all little-endian, gzip-compressed unless noted):
  index_<side>.bin.gz : u16 side mask, then entries of
    { u16 entry size (name length + 8), u8 name length, name, u8 chunk, u32 offset }
    sorted by name, then chunk. The offset points at a match list inside the batch.
  batch_NNN.bin.gz    : record blocks, then match lists.

Match list: run of u32 record offsets ended by 0xFFFFFFFF.
Record: one (u8 name length, name, u8 owner length, owner) pair per side present in
  the mask (bit order mojmap=1, yarn=2, intermediary=4), then u8 descriptor length,
  descriptor, u8 kind (0 class, 1 field, 2 method).

A zero length anywhere in the record information means the name is effectively
null and is reported as None.
"""

import struct
from dataclasses import dataclass

SIDE_ORDER = ["mojmap", "yarn", "intermediary"]
SIDE_BITS = {"mojmap": 1 << 0, "yarn": 1 << 1, "intermediary": 1 << 2}
KIND_NAMES = {0: "class", 1: "field", 2: "method"}
END_OF_MATCHES = 0xFFFFFFFF
MAX_MATCHES = 4_000_000


@dataclass
class IndexEntry:
    name: str
    chunk: int
    offset: int


@dataclass
class Index:
    mask: int
    entries: list[IndexEntry]


@dataclass
class SideEntry:
    name: str | None
    owner: str | None


@dataclass
class Record:
    sides: dict[str, SideEntry]
    descriptor: str
    kind: str


def parse_index(data: bytes) -> Index:
    if len(data) < 2:
        raise ValueError("Index file is truncated (no side mask)")
    (mask,) = struct.unpack_from("<H", data, 0)
    entries: list[IndexEntry] = []
    pos = 2
    while pos < len(data):
        if pos + 3 > len(data):
            raise ValueError(f"Index entry at byte {pos} is truncated (header)")
        (size,) = struct.unpack_from("<H", data, pos)
        name_length = data[pos + 2]
        if size != name_length + 8:
            raise ValueError(f"Bad index entry size {size} at byte {pos} (expected {name_length + 8})")
        if pos + size > len(data):
            raise ValueError(f"Index entry at byte {pos} runs past the end of the file")
        name_start = pos + 3
        name = data[name_start:name_start + name_length].decode("utf-8")
        chunk = data[name_start + name_length]
        (offset,) = struct.unpack_from("<I", data, name_start + name_length + 1)
        entries.append(IndexEntry(name, chunk, offset))
        pos += size
    return Index(mask, entries)


def sides_from_mask(mask: int) -> list[str]:
    return [side for side in SIDE_ORDER if mask & SIDE_BITS[side]]


def _lower_bound(names: list[str], query: str) -> int:
    # First index whose name is >= query (entries are sorted by name).
    lo, hi = 0, len(names)
    while lo < hi:
        mid = (lo + hi) // 2
        if names[mid] < query:
            lo = mid + 1
        else:
            hi = mid
    return lo


def search_entries(entries: list[IndexEntry], query: str, mode: str) -> list[IndexEntry]:
    if mode in ("exact", "prefix"):
        names = [entry.name for entry in entries]
        start = _lower_bound(names, query)
        matches = []
        for entry in entries[start:]:
            if mode == "exact":
                if entry.name != query:
                    break
            elif not entry.name.startswith(query):
                break
            matches.append(entry)
        return matches
    needle = query.lower()  # contains is case-insensitive
    return [entry for entry in entries if needle in entry.name.lower()]


def read_match_list(data: bytes, start: int) -> list[int]:
    offsets: list[int] = []
    pos = start
    for _ in range(MAX_MATCHES + 1):
        if pos + 4 > len(data):
            raise ValueError("Match list runs past the end of the batch")
        (offset,) = struct.unpack_from("<I", data, pos)
        pos += 4
        if offset == END_OF_MATCHES:
            return offsets
        offsets.append(offset)
    raise ValueError("Match list is unreasonably long")


def decode_record(data: bytes, offset: int, sides: list[str]) -> Record:
    pos = offset

    def read_length_prefixed() -> str | None:
        nonlocal pos
        length = data[pos]
        pos += 1
        value = data[pos:pos + length].decode("utf-8") if length else None
        pos += length
        return value

    record_sides: dict[str, SideEntry] = {}
    for side in sides:
        name = read_length_prefixed()
        owner = read_length_prefixed()
        record_sides[side] = SideEntry(name, owner)

    descriptor_length = data[pos]
    pos += 1
    descriptor = data[pos:pos + descriptor_length].decode("utf-8") if descriptor_length else ""
    pos += descriptor_length
    kind_code = data[pos]
    kind = KIND_NAMES.get(kind_code, f"kind {kind_code}")
    return Record(record_sides, descriptor, kind)

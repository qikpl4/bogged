"""Lookup orchestration: index first, then only the batches with matches."""

from dataclasses import dataclass

import binary
import sources


@dataclass
class LookupResult:
    records: list[binary.Record]
    files_fetched: int
    bytes_fetched: int


def lookup(base_url: str, version: str, side: str, query: str, mode: str) -> LookupResult:
    base_url = sources.normalize_base_url(base_url)
    stats = {"files": 0, "bytes": 0}

    def load(path: str) -> bytes:
        data = sources.load_file(base_url, f"{version}/{path}")
        stats["files"] += 1
        stats["bytes"] += len(data)
        return data

    index = binary.parse_index(load(sources.index_file(side)))
    sides = binary.sides_from_mask(index.mask)
    matches = binary.search_entries(index.entries, query, mode)

    wanted_chunks = sorted({match.chunk for match in matches})
    batches = {chunk: load(sources.batch_file(chunk)) for chunk in wanted_chunks}

    records: list[binary.Record] = []
    for match in matches:
        data = batches[match.chunk]
        for record_offset in binary.read_match_list(data, match.offset):
            records.append(binary.decode_record(data, record_offset, sides))

    return LookupResult(records, stats["files"], stats["bytes"])

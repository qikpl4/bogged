"""Read a version directory written by binfmt.writer."""

from __future__ import annotations

import gzip
import struct
from pathlib import Path

from .layout import BATCH_FILE, END_OF_MATCHES, INDEX_FILE, KIND_NAMES, SIDE_ORDER, sides_from_mask


class BinaryVersion:
    def __init__(self, version_dir: Path) -> None:
        self.directory = version_dir
        self.side_mask = 0
        self._entries: dict[str, dict[bytes, list[tuple[int, int]]]] = {}
        for side in SIDE_ORDER:
            raw = gzip.decompress((version_dir / INDEX_FILE.format(side)).read_bytes())
            (mask,) = struct.unpack_from("<H", raw, 0)
            if self.side_mask and mask != self.side_mask:
                raise ValueError(f"{version_dir}: index files disagree on the side mask")
            self.side_mask = mask
            entries: dict[bytes, list[tuple[int, int]]] = {}
            position = 2
            while position < len(raw):
                (size,) = struct.unpack_from("<H", raw, position)
                name_length = raw[position + 2]
                if size != name_length + 8:
                    raise ValueError(f"{INDEX_FILE.format(side)}: bad entry size {size} at byte {position}")
                name = raw[position + 3:position + 3 + name_length]
                chunk = raw[position + 3 + name_length]
                (start,) = struct.unpack_from("<I", raw, position + 4 + name_length)
                entries.setdefault(name, []).append((chunk, start))
                position += size
            self._entries[side] = entries
        self.sides = sides_from_mask(self.side_mask)
        self._batches: dict[int, bytes] = {}

    def _batch(self, chunk: int) -> bytes:
        if chunk not in self._batches:
            self._batches[chunk] = gzip.decompress((self.directory / BATCH_FILE.format(chunk)).read_bytes())
        return self._batches[chunk]

    def _decode(self, data: bytes, offset: int) -> tuple[tuple[tuple[str | None, str | None], ...], str, str]:
        position = offset
        sides: list[tuple[str | None, str | None]] = []
        for _ in self.sides:
            pair: list[str | None] = []
            for _field in range(2):
                length = data[position]
                position += 1
                text = data[position:position + length].decode("utf-8")
                position += length
                pair.append(text if length else None)
            sides.append((pair[0], pair[1]))
        length = data[position]
        position += 1
        descriptor = data[position:position + length].decode("utf-8")
        position += length
        kind = KIND_NAMES[data[position]]
        return tuple(sides), descriptor, kind

    def lookup(self, side: str, name: str) -> list[tuple[tuple[tuple[str | None, str | None], ...], str, str]]:
        """Return every record whose `side` name is `name`, as (sides, descriptor, kind).

        `sides` is positional, in the order of `self.sides`, with each entry a (name, owner class) pair.
        """
        results = []
        for chunk, start in self._entries[side].get(name.encode("utf-8"), []):
            data = self._batch(chunk)
            position = start
            while True:
                (offset,) = struct.unpack_from("<I", data, position)
                if offset == END_OF_MATCHES:
                    break
                results.append(self._decode(data, offset))
                position += 4
        return results

    def names(self, side: str) -> list[str]:
        return [name.decode("utf-8") for name in self._entries[side]]

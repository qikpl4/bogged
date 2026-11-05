/* Binary format parsing for the packed mapping data.
 *
 * Layout (all little-endian, gzip-compressed unless noted):
 *   index_<side>.bin.gz : u16 side mask, then entries of
 *     { u16 entry size (name length + 8), u8 name length, name, u8 chunk, u32 offset }
 *     sorted by name, then chunk. The offset points at a match list inside the batch.
 *   batch_NNN.bin.gz    : record blocks, then match lists.
 *
 * Match list: run of u32 record offsets ended by 0xFFFFFFFF.
 * Record: one (u8 name length, name, u8 owner length, owner) pair per side present in
 *   the mask (bit order mojmap=1, yarn=2, intermediary=4), then u8 descriptor length,
 *   descriptor, u8 kind (0 class, 1 field, 2 method).
 */
import { END_OF_MATCHES, KIND_NAMES, SIDE_BITS, SIDE_ORDER } from './constants.js';

const textDecoder = new TextDecoder();

export function parseIndex(bytes) {
  if (bytes.length < 2) throw new Error('Index file is truncated (no side mask)');
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  const mask = view.getUint16(0, true);
  const entries = [];
  let pos = 2;
  while (pos < bytes.length) {
    const size = view.getUint16(pos, true);
    const nameLength = bytes[pos + 2];
    if (size !== nameLength + 8) {
      throw new Error(`Bad index entry size ${size} at byte ${pos} (expected ${nameLength + 8})`);
    }
    const nameStart = pos + 3;
    const name = textDecoder.decode(bytes.subarray(nameStart, nameStart + nameLength));
    const chunk = bytes[nameStart + nameLength];
    const offset = view.getUint32(nameStart + nameLength + 1, true);
    entries.push({ name, chunk, offset });
    pos += size;
  }
  return { mask, entries };
}

export function sidesFromMask(mask) {
  return SIDE_ORDER.filter((side) => mask & SIDE_BITS[side]);
}

export function lowerBound(entries, query) {
  // First index whose entry name is >= query (entries are sorted by name).
  let lo = 0;
  let hi = entries.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    if (entries[mid].name < query) lo = mid + 1; else hi = mid;
  }
  return lo;
}

export function searchEntries(entries, query, mode) {
  const matches = [];
  if (mode === 'exact') {
    for (let i = lowerBound(entries, query); i < entries.length && entries[i].name === query; i += 1) {
      matches.push(entries[i]);
    }
    return matches;
  }
  if (mode === 'prefix') {
    for (let i = lowerBound(entries, query); i < entries.length && entries[i].name.startsWith(query); i += 1) {
      matches.push(entries[i]);
    }
    return matches;
  }
  const needle = query.toLowerCase(); // contains is case-insensitive
  for (const entry of entries) {
    if (entry.name.toLowerCase().includes(needle)) matches.push(entry);
  }
  return matches;
}

export function readMatchList(data, start) {
  const view = new DataView(data.buffer, data.byteOffset, data.byteLength);
  const offsets = [];
  let pos = start;
  for (;;) {
    if (pos + 4 > data.length) throw new Error('Match list runs past the end of the batch');
    const offset = view.getUint32(pos, true);
    pos += 4;
    if (offset === END_OF_MATCHES) return offsets;
    offsets.push(offset);
    if (offsets.length > 4_000_000) throw new Error('Match list is unreasonably long');
  }
}

export function decodeRecord(data, offset, sides) {
  let pos = offset;
  const readLengthPrefixed = () => {
    const length = data[pos];
    pos += 1;
    const value = length ? textDecoder.decode(data.subarray(pos, pos + length)) : null;
    pos += length;
    return value;
  };
  const recordSides = {};
  for (const side of sides) {
    recordSides[side] = { name: readLengthPrefixed(), owner: readLengthPrefixed() };
  }
  const descriptorLength = data[pos];
  pos += 1;
  const descriptor = descriptorLength ? textDecoder.decode(data.subarray(pos, pos + descriptorLength)) : '';
  pos += descriptorLength;
  const kindCode = data[pos];
  return { sides: recordSides, descriptor, kind: KIND_NAMES[kindCode] ?? `kind ${kindCode}` };
}

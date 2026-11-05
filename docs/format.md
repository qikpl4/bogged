# Bogged format

Part of the work in Bogged includes a compact and fast transport format for looking up different Java names that point to the same code.

There are two components of it: the entrypoint index and chunks with record information and series of grouped equivalents.

All components can be gzip-compressed and offset values always refer to the decompressed value. Readers are expected to gracefully handle uncompressed data.

Strings are in UTF-8 format.

By design, all name fields only support up to 255 characters. As such, a handful of names are skipped.

## Entrypoint index format

Consists of the header and repeated records of one side for looking up the chunk and the correct offset to get the other sides. There is no terminator.

### Header

| Byte count | Note |
| --- | --- |
| 2 | Bitmask. See Appendix A. |

### Entry

| Byte count | Note |
| --- | --- |
| 2 | Total length of the entry |
| 1 | Length of the name |
| * | The name |
| 1 | The ID of the chunk. Each version can have up to 255 chunks. |
| 4 | Little endian offset in the chunk to look up the equivalent list |

## Chunk format

Consists of an array of repeated record information, followed by the equivalent lists. There is no split and each equivalent list has a terminator.

### Record information

A zero length anywhere in the record information means the name is effectively null and shall be skipped or omitted.

#### Side-specific

This is repeated every `popcnt(index_header)` times, i.e. the amount of sides.

| Byte count | Note |
| --- | --- |
| 1 | Length of the name |
| * | The name |
| 1 | Length of the owner class |
| * | The owner class |

#### Common

This is not repeated.

| Byte count | Note |
| --- | --- |
| 1 | Length of the descriptor |
| * | The descriptor |
| 1 | Type of record. See Appendix B. |

### Equivalent list

The equivalent list is repeated 32-bit little endian offsets in the chunk to look up the record information followed by `0xFFFFFFFF`.

## Appendix

### A. Mapping project bitfield

The 16-bit bitfield specifies the included mapping projects. Currently, the definition is well-defined. By design there are only 16 possible mapping projects.

| Bit | Project |
| --- | --- |
| 0 | Mojmap |
| 1 | Yarn |
| 2 | Intermediary |
| 3+ | Reserved for future use |

### B. Record types

| Value | Type |
| --- | --- |
| 0 | Class |
| 1 | Field |
| 2 | Method |

# Bogged Format

Bogged stores Minecraft mappings for many versions in a compact binary format, one
directory per version. Each version is split into a small set of **index** files and
**batch** files so that a reader can locate a name by downloading only a tiny index,
then fetching just the batch files that actually contain matches.

This document is a complete specification. After reading it you should be able to
write your own reader and writer in any language.

## 1. Data model

A mapping entry — called a **record** — describes one class, field, or method and
holds an optional name for each *side* (naming scheme) it is known in.

- **Side**: one naming scheme. Three are defined, and the header reserves room for
  eight total:

  | Side           | Bit value | Meaning                                 |
  | -------------- | --------- | --------------------------------------- |
  | `mojmap`       | `1 << 0`  | Mojang official names (obfuscated)      |
  | `yarn`         | `1 << 1`  | Fabric Yarn names                       |
  | `intermediary` | `1 << 2`  | Fabric Intermediary names               |

- **Kind**: what the record is — `0` = class, `1` = field, `2` = method.
- **Descriptor**: the JVM type descriptor (for example `(I)V` or `Lnet/minecraft/Foo;`),
  or empty when not applicable.
- Each side entry is a pair `(name, owner)`:
  - `name` — the name in that side's scheme (for example `getPos`).
  - `owner` — the owning class name in that side's scheme. For a class record, or
    when the owner is implied, this is empty.
  - Both `name` and `owner` may be empty when the record has no name for that side.

A record may have names for any subset of the sides present in the file.

## 2. On-disk layout

A build produces an output directory containing:

```
<output>/
  versions.json                  # plain JSON array of version names, uncompressed
  <version>/
    index_mojmap.bin.gz          # one index per side that is present
    index_yarn.bin.gz
    index_intermediary.bin.gz
    batch_000.bin.gz             # exactly BATCH_COUNT batch files
    batch_001.bin.gz
    ...
    batch_015.bin.gz
```

- **Version names** are used verbatim as directory names.
- **Every `.bin.gz` file is a standard gzip stream** (RFC 1952). Decompress it
  first; all offsets and sizes below refer to the **decompressed** bytes. A reader
  may accept already-decompressed input defensively, since some servers
  transparently decompress `.gz` responses.
- **All integers are little-endian.**
- **Variable-length fields** are encoded as a one-byte unsigned length `L` followed
  by `L` bytes of content. A length of `0` means "absent / empty". Because the
  length prefix is a single byte, no field may exceed **255 bytes**; a writer must
  drop records that would violate this.
- **Text is UTF-8.**

### 2.1 Constants

| Name              | Value        | Meaning                                            |
| ----------------- | ------------ | -------------------------------------------------- |
| `BATCH_COUNT`     | `16`         | Recommended batch files per version.                |
| `SHUFFLE_SEED`    | `67`         | Recommended seed for the record→batch shuffle.      |
| `MAX_FIELD_LENGTH`| `255`        | Maximum length of any variable-length field.        |
| `END_OF_MATCHES`  | `0xFFFFFFFF` | Terminator for a match list (never a valid offset). |
| `MAX_OFFSET`      | `0xFFFFFFFE` | Largest offset a batch may use.                     |

## 3. `versions.json`

An uncompressed JSON array of version directory names, suitable for populating a
version picker:

```json
[
  "1.20.6",
  "1.21.5",
  "1.21.11"
]
```

Versions are sorted numerically (so `1.21.5` sorts before `1.21.11`), and only
directories that contain an `index_mojmap.bin.gz` are listed. A reader can ignore
this file entirely and discover versions by listing directories instead.

## 4. Index file

Path: `index_<side>.bin.gz`, one per present side. The index maps a name from that
side to the locations of its records. It is sorted by `(name, chunk)`, enabling
binary search.

After gzip decompression:

```
u16  side_mask                 # bitmask of sides present in this version
Entry[] entries                # repeated until end of file
```

Each entry:

```
u16  size                      # total entry size; MUST equal name_length + 8
u8   name_length               # L
u8[] name                      # L bytes, UTF-8
u8   chunk                     # batch file number (0 .. BATCH_COUNT-1)
u32  offset                    # start of a match list inside that batch (decompressed)
```

- `side_mask` must be identical in every index file of a version; a reader should
  reject indices that disagree.
- There is **no entry count**; read entries until you reach the end of the
  decompressed bytes.
- `size` is redundant (`name_length + 8`) and exists as a self-check. `8` = 2
  (size) + 1 (name_length) + 1 (chunk) + 4 (offset).
- A name may appear **multiple times** — once per batch in which a record carries
  that name. Collect all entries for a name before reading records.

Pseudocode:

```python
mask = read_u16()
pos = 2
entries = []
while pos < len(data):
    size = read_u16(pos)
    name_length = data[pos + 2]
    assert size == name_length + 8
    name = utf8(data[pos + 3 : pos + 3 + name_length])
    chunk = data[pos + 3 + name_length]
    offset = read_u32(pos + 4 + name_length)
    entries.append((name, chunk, offset))
    pos += size
```

To look up a name, binary-search for it. Names are ordered by their UTF-8 bytes,
which matches code-point order for ASCII names.

## 5. Batch file

Path: `batch_NNN.bin.gz`, where `NNN` is the zero-padded, three-digit batch number
(`batch_000.bin.gz` … `batch_015.bin.gz`). Batch files are always all present; some
may hold no records.

After gzip decompression, a batch is two concatenated regions:

```
Record[]        record blocks back-to-back
MatchList[]     match lists, each ended by 0xFFFFFFFF
```

The exact split point is not stored. Record blocks come first, then match lists;
an offset from the index points into the match-list region, and each match-list
offset points back into the record-block region. Readers only need the offsets from
the index, so they never have to compute the boundary.

### 5.1 Record block

A record block, starting at a byte offset referenced by a match list:

```
# for each side present in the mask, in bit order (mojmap, yarn, intermediary):
u8   name_length               # L, may be 0
u8[] name                      # L bytes, UTF-8
u8   owner_length              # L, may be 0
u8[] owner                     # L bytes, UTF-8
# then:
u8   descriptor_length         # L, may be 0
u8[] descriptor                # L bytes, UTF-8
u8   kind                      # 0 class, 1 field, 2 method
```

Notes:

- The number of `(name, owner)` pairs is exactly the number of sides set in the
  index `side_mask`, and they always appear in canonical bit order
  (`mojmap`, `yarn`, `intermediary`). Sides absent from the mask are omitted
  entirely, so a reader must decode only the sides it knows are present.
- A `0` length means the field is absent. For a side with no name, both `name` and
  `owner` are `0`-length.
- If `descriptor_length` is `0`, the descriptor is the empty string. A writer
  should emit `0` for a record with no descriptor, and a reader may treat it as an
  empty or absent value as it prefers.

### 5.2 Match list

A match list starts at an offset given by an index entry:

```
u32[] offsets      # record block offsets
u32   END_OF_MATCHES   # 0xFFFFFFFF terminator
```

Read `u32` values until you hit `0xFFFFFFFF`; each preceding value is a byte offset
into the same batch where a record block begins. A record carrying the same name
for the same side is listed once per occurrence.

### 5.3 Lookup walkthrough

To resolve name `N` in side `S`:

1. Read `index_<S>.bin.gz`, decompress, parse `side_mask` and entries.
2. Find all entries with `name == N` (binary search, then scan equal names). Each
   gives a `(chunk, offset)`.
3. For each such entry, load `batch_<chunk>.bin.gz`, decompress.
4. At `offset`, read the match list until `0xFFFFFFFF`.
5. For each record offset in the list, decode a record block using `side_mask`.
6. Concatenate results across all entries and chunks.

## 6. Byte-level example

A version built with only `mojmap` (mask `0x0001`) has one side. A record for the
method `getPos` with owner `Foo`, descriptor `()V`, kind method (`2`):

```
0x04 "getPos"        # mojmap name
0x03 "Foo"           # mojmap owner
0x03 "()V"           # descriptor
0x02                 # kind = method
```

If instead the mask were `0x0003` (`mojmap | yarn`) and the yarn side were absent,
the block would begin with two pairs, the first filled and the second empty:

```
0x04 "getPos"  0x03 "Foo"   # mojmap
0x00           0x00         # yarn: no name, no owner
0x03 "()V"     0x02         # descriptor, kind
```

## 7. Writing a file

A minimal writer proceeds as follows (per version):

1. **Prepare records.** For each record, encode each side as `(name, owner)` in
   canonical order; use empty bytes for sides the record lacks. Drop any record
   whose name, owner, or descriptor exceeds 255 bytes.
2. **Assign records to batches.** Build the list of record indices, shuffle it with
   a seeded PRNG (`SHUFFLE_SEED = 67`), and split into `BATCH_COUNT = 16`
   contiguous slices of `ceil(count / 16)` records each (at least one slot per
   batch). The shuffle spreads similar records apart, which improves gzip ratios.
   A reader does **not** depend on this ordering — it is purely a size optimization,
   though matching it makes output byte-for-byte reproducible.
3. **For each batch**, build one byte buffer:
   - Append every assigned record block, remembering each record's start offset.
   - Group records by `(side_position, name)`. For each group, sorted by
     `(side_position, name)`, append the members' `u32` offsets followed by
     `0xFFFFFFFF`, and record `(name, chunk, start_of_this_match_list)` for the
     matching side's index.
   - Gzip the buffer (a fixed mtime such as `0` keeps the output reproducible)
     and write `batch_NNN.bin.gz`.
4. **For each side**, build its index:
   - A `u16 side_mask`, then all `(name, chunk, offset)` entries sorted by
     `(name, chunk)`, each encoded as `u16 (name_length + 8)`, `u8 name_length`,
     name bytes, `u8 chunk`, `u32 offset`.
   - Gzip and write `index_<side>.bin.gz`. Writing an index file for **every** side
     in the canonical order, even those with no entries, is recommended.
5. **Write `versions.json`** listing the version directories (numeric sort).

## 8. Reading a file

See sections 4–5 for the parsing rules and 5.3 for the lookup algorithm.

Validation a robust reader should perform:

- Reject a truncated index (fewer than 2 bytes).
- Verify each index entry's `size == name_length + 8`.
- Verify the `side_mask` matches across all index files of a version.
- Bound each match list (a terminator must appear before the end of the buffer).
- Stop decoding a record if it runs past the end of the batch.

## 9. Compatibility notes

- The format reserves bits up to `1 << 7` in `side_mask` for future sides. A reader
  that encounters unknown bits should skip the corresponding `(name, owner)` pair
  (two length-prefixed fields) rather than fail, since those pairs are still
  present in every record block in canonical order.
- `BATCH_COUNT` may be increased in future builds but must stay ≤ 256 to fit the
  one-byte `chunk`. Readers must not hard-code 16 when reading; they should use the
  `chunk` value from the index. Writers may choose a different count.
- Batch contents are order-independent; no particular shuffle is required.
- The gzip layer carries no format information. Any valid gzip stream is accepted,
  and readers should tolerate input that is already decompressed.

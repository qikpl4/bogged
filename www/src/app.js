/* Mapping Lookup — static viewer for the packed binary mapping format.
 *
 * Layout (all little-endian, gzip-compressed unless noted):
 *   index_<side>.bin.gz : u16 side mask, then entries of
 *     { u16 entry size (name length + 8), u8 name length, name, u8 chunk, u32 offset }
 *     sorted by name, then chunk. The offset points at a match list inside the batch.
 *   batch_NNN.bin.gz    : record blocks, then match lists.
 *   versions.json       : plain JSON array of version names (uncompressed, a few bytes).
 *
 * Match list: run of u32 record offsets ended by 0xFFFFFFFF.
 * Record: one (u8 name length, name, u8 owner length, owner) pair per side present in
 *   the mask (bit order mojmap=1, yarn=2, intermediary=4), then u8 descriptor length,
 *   descriptor, u8 kind (0 class, 1 field, 2 method).
 */
import pako from 'pako';
import '@picocss/pico/css/pico.min.css';
import './style.css';

const SIDE_ORDER = ['mojmap', 'yarn', 'intermediary'];
const SIDE_BITS = { mojmap: 1 << 0, yarn: 1 << 1, intermediary: 1 << 2 };
const KIND_NAMES = { 0: 'class', 1: 'field', 2: 'method' };
const END_OF_MATCHES = 0xffffffff;
const GZIP_MAGIC_0 = 0x1f;
const GZIP_MAGIC_1 = 0x8b;

const textDecoder = new TextDecoder();

const indexFile = (side) => `index_${side}.bin.gz`;
const batchFile = (chunk) => `batch_${String(chunk).padStart(3, '0')}.bin.gz`;

const $ = (selector) => document.querySelector(selector);
const form = $('#lookup-form');
const versionSelect = $('#version');
const queryInput = $('#query');
const baseUrlInput = $('#base-url');
const matchModeSelect = $('#match-mode');
const maxResultsInput = $('#max-results');
const lookupButton = $('#lookup-button');
const clearCacheButton = $('#clear-cache');
const progressArea = $('#progress-area');
const progressEl = $('#progress');
const progressText = $('#progress-text');
const errorBox = $('#error');
const resultsSection = $('#results');
const resultsSummary = $('#results-summary');
const resultsMeta = $('#results-meta');
const truncatedNote = $('#truncated-note');
const resultsBody = $('#results-body');
const resultsTable = $('#results-table');

/* ---------- cache ---------- */

const cache = new Map(); // key -> parsed index | decompressed batch bytes | Promise thereof

function cacheKey(...parts) {
  return [baseUrl(), ...parts].join('|');
}

function cacheGetOrLoad(key, loader) {
  if (!cache.has(key)) {
    cache.set(key, loader().catch((error) => {
      cache.delete(key); // don't cache failures
      throw error;
    }));
  }
  return cache.get(key);
}

/* ---------- fetching ---------- */

function baseUrl() {
  return (baseUrlInput.value.trim() || 'data').replace(/\/+$/, '');
}

function dataUrl(path) {
  return `${baseUrl()}/${path}`;
}

function formatBytes(bytes) {
  if (!Number.isFinite(bytes)) return '?';
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
}

async function fetchBytes(url, onBytes) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Could not fetch ${url}\nHTTP ${response.status} ${response.statusText}`);
  }
  const total = Number(response.headers.get('Content-Length')) || 0;
  if (!response.body) {
    const buffer = await response.arrayBuffer();
    if (onBytes) onBytes(buffer.byteLength, buffer.byteLength);
    return new Uint8Array(buffer);
  }
  const reader = response.body.getReader();
  const chunks = [];
  let received = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    if (value) {
      chunks.push(value);
      received += value.length;
      if (onBytes) onBytes(received, total);
    }
  }
  const out = new Uint8Array(received);
  let offset = 0;
  for (const chunk of chunks) {
    out.set(chunk, offset);
    offset += chunk.length;
  }
  return out;
}

function gunzip(bytes) {
  // Guard against servers that transparently decompress .gz responses.
  if (bytes.length >= 2 && bytes[0] === GZIP_MAGIC_0 && bytes[1] === GZIP_MAGIC_1) {
    return pako.ungzip(bytes);
  }
  return bytes;
}

async function fetchGunzipped(url, onBytes) {
  const raw = await fetchBytes(url, onBytes);
  try {
    return gunzip(raw);
  } catch (error) {
    throw new Error(`Could not decompress ${url}\n${error.message ?? error}`);
  }
}

/* ---------- progress bar ---------- */

function showProgress(max, value, text) {
  progressArea.hidden = false;
  progressEl.max = max;
  if (value === null) {
    progressEl.removeAttribute('value'); // indeterminate
  } else {
    progressEl.value = value;
  }
  if (text !== undefined) progressText.textContent = text;
}

function hideProgress() {
  progressArea.hidden = true;
}

function showError(error) {
  errorBox.hidden = false;
  errorBox.textContent = error?.message ?? String(error);
}

function hideError() {
  errorBox.hidden = true;
  errorBox.textContent = '';
}

/* ---------- versions.json ---------- */

async function loadVersions() {
  const previous = versionSelect.value;
  versionSelect.disabled = true;
  versionSelect.innerHTML = '<option>Loading…</option>';
  showProgress(1, null, `Fetching versions.json…`);
  hideError();
  try {
    const response = await fetch(dataUrl('versions.json'));
    if (!response.ok) {
      throw new Error(`Could not fetch versions.json\nHTTP ${response.status} ${response.statusText}`);
    }
    const versions = await response.json();
    if (!Array.isArray(versions) || versions.some((v) => typeof v !== 'string')) {
      throw new Error('versions.json is not a JSON array of version names');
    }
    versionSelect.innerHTML = '';
    for (const version of versions) {
      const option = document.createElement('option');
      option.value = version;
      option.textContent = version;
      versionSelect.appendChild(option);
    }
    if (versions.includes(previous)) versionSelect.value = previous;
    hideProgress();
  } catch (error) {
    versionSelect.innerHTML = '<option value="">Unavailable</option>';
    showError(error);
    hideProgress();
  } finally {
    versionSelect.disabled = false;
  }
}

/* ---------- binary format ---------- */

function parseIndex(bytes) {
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

function sidesFromMask(mask) {
  return SIDE_ORDER.filter((side) => mask & SIDE_BITS[side]);
}

function lowerBound(entries, query) {
  // First index whose entry name is >= query (entries are sorted by name).
  let lo = 0;
  let hi = entries.length;
  while (lo < hi) {
    const mid = (lo + hi) >>> 1;
    // eslint-disable-next-line no-nested-ternary
    if (entries[mid].name < query) lo = mid + 1; else hi = mid;
  }
  return lo;
}

function searchEntries(entries, query, mode, limit) {
  const matches = [];
  if (mode === 'exact') {
    for (let i = lowerBound(entries, query); i < entries.length && entries[i].name === query; i += 1) {
      matches.push(entries[i]);
      if (matches.length >= limit) break;
    }
    return matches;
  }
  if (mode === 'prefix') {
    for (let i = lowerBound(entries, query); i < entries.length && entries[i].name.startsWith(query); i += 1) {
      matches.push(entries[i]);
      if (matches.length >= limit) break;
    }
    return matches;
  }
  const needle = query.toLowerCase(); // contains is case-insensitive
  for (const entry of entries) {
    if (entry.name.toLowerCase().includes(needle)) {
      matches.push(entry);
      if (matches.length >= limit) break;
    }
  }
  return matches;
}

function readMatchList(data, start) {
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

function decodeRecord(data, offset, sides) {
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

/* ---------- loading with progress ---------- */

let bytesFetched = 0;
let filesFetched = 0;
let cacheHits = 0;

function resetFetchStats() {
  bytesFetched = 0;
  filesFetched = 0;
  cacheHits = 0;
}

async function loadIndex(version, side) {
  const key = cacheKey(version, 'index', side);
  const cached = cache.get(key);
  if (cached) {
    cacheHits += 1;
    return cached;
  }
  const file = indexFile(side);
  return cacheGetOrLoad(key, async () => {
    const bytes = await fetchGunzipped(dataUrl(`${version}/${file}`), (received, total) => {
      progressText.textContent = `Fetching ${file}… ${formatBytes(received)}${total ? ` / ${formatBytes(total)}` : ''}`;
    });
    bytesFetched += bytes.length;
    filesFetched += 1;
    return parseIndex(bytes);
  });
}

async function loadBatch(version, chunk) {
  const key = cacheKey(version, 'batch', chunk);
  const cached = cache.get(key);
  if (cached) {
    cacheHits += 1;
    return cached;
  }
  const file = batchFile(chunk);
  return cacheGetOrLoad(key, async () => {
    const bytes = await fetchGunzipped(dataUrl(`${version}/${file}`));
    bytesFetched += bytes.length;
    filesFetched += 1;
    return bytes;
  });
}

/* ---------- lookup ---------- */

function currentSide() {
  return form.elements.side.value;
}

function maxResults() {
  const value = Number.parseInt(maxResultsInput.value, 10);
  return Number.isFinite(value) ? Math.min(Math.max(value, 1), 1000) : 100;
}

async function lookup() {
  hideError();
  const side = currentSide();
  const version = versionSelect.value;
  const query = queryInput.value.trim();
  if (!version || !query) return;

  const mode = matchModeSelect.value;
  const limit = maxResults();
  resetFetchStats();
  lookupButton.disabled = true;
  const started = performance.now();

  // Phase 1: index for the selected side only.
  showProgress(1, null, `Fetching ${indexFile(side)}…`);
  try {
    const index = await loadIndex(version, side);
    const matches = searchEntries(index.entries, query, mode, limit);
    const wantedChunks = [...new Set(matches.map((match) => match.chunk))].sort((a, b) => a - b);

    // Phase 2: only the batch files that hold matches.
    const totalSteps = 1 + wantedChunks.length;
    let chunksDone = 0;
    showProgress(totalSteps, 1, wantedChunks.length
      ? `Index loaded — fetching ${wantedChunks.length} batch ${wantedChunks.length === 1 ? 'file' : 'files'}…`
      : 'Index loaded — no matching batch files needed');

    const batches = new Map();
    await Promise.all(wantedChunks.map(async (chunk) => {
      batches.set(chunk, await loadBatch(version, chunk));
      chunksDone += 1;
      showProgress(totalSteps, 1 + chunksDone, `Fetching ${batchFile(chunk)}… (${chunksDone}/${wantedChunks.length})`);
    }));

    // Phase 3: decode records (entirely local).
    const sides = sidesFromMask(index.mask);
    const rows = [];
    let truncated = false;
    for (const match of matches) {
      const data = batches.get(match.chunk);
      for (const recordOffset of readMatchList(data, match.offset)) {
        rows.push(decodeRecord(data, recordOffset, sides));
        if (rows.length >= limit) { truncated = true; break; }
      }
      if (truncated) break;
    }

    hideProgress();
    renderResults(rows, { side, version, query, truncated, mode });
    const elapsed = Math.round(performance.now() - started);
    const parts = [`${filesFetched} ${filesFetched === 1 ? 'file' : 'files'} fetched (${formatBytes(bytesFetched)} over the wire)`];
    if (cacheHits) parts.push(`${cacheHits} served from memory`);
    parts.push(`${elapsed} ms`);
    resultsMeta.textContent = parts.join(' · ');
  } catch (error) {
    hideProgress();
    showError(error);
    resultsSection.hidden = true;
  } finally {
    lookupButton.disabled = false;
  }
}

/* ---------- rendering ---------- */

function cellForSide(record, side) {
  const td = document.createElement('td');
  td.dataset.side = side;
  const entry = record.sides[side];
  if (!entry || !entry.name) {
    const absent = document.createElement('span');
    absent.className = 'cell-absent';
    absent.textContent = '—';
    td.appendChild(absent);
    return td;
  }
  const name = document.createElement('span');
  name.className = 'cell-name';
  name.textContent = entry.name;
  td.appendChild(name);
  if (entry.owner) {
    const owner = document.createElement('span');
    owner.className = 'cell-owner';
    owner.textContent = entry.owner;
    td.appendChild(owner);
  }
  return td;
}

function renderResults(rows, { side, version, query, truncated, mode }) {
  resultsSection.hidden = false;
  resultsTable.dataset.activeSide = side;
  resultsSummary.textContent = `Results (${rows.length})`;
  truncatedNote.hidden = !truncated;
  if (truncated) {
    truncatedNote.textContent = `More results exist — showing the first ${rows.length} (Max results). Narrow the query or raise the limit in Settings.`;
  }
  resultsBody.replaceChildren();

  if (rows.length === 0) {
    const tr = document.createElement('tr');
    const td = document.createElement('td');
    td.colSpan = 5;
    td.className = 'cell-absent';
    const modeLabel = mode === 'exact' ? 'exactly matching' : mode === 'prefix' ? 'starting with' : 'containing';
    td.textContent = `No ${modeLabel} “${query}” in ${version} (${side}).`;
    tr.appendChild(td);
    resultsBody.appendChild(tr);
    return;
  }

  for (const record of rows) {
    const tr = document.createElement('tr');

    const kindTd = document.createElement('td');
    const badge = document.createElement('span');
    badge.className = 'kind-badge';
    badge.textContent = record.kind;
    kindTd.appendChild(badge);
    tr.appendChild(kindTd);

    for (const sideName of SIDE_ORDER) {
      tr.appendChild(cellForSide(record, sideName));
    }

    const descriptorTd = document.createElement('td');
    if (record.descriptor) {
      const code = document.createElement('code');
      code.textContent = record.descriptor;
      descriptorTd.appendChild(code);
    } else {
      const absent = document.createElement('span');
      absent.className = 'cell-absent';
      absent.textContent = '—';
      descriptorTd.appendChild(absent);
    }
    tr.appendChild(descriptorTd);

    resultsBody.appendChild(tr);
  }
}

/* ---------- wiring ---------- */

form.addEventListener('submit', (event) => {
  event.preventDefault();
  lookup();
});

// versions.json is tiny — revalidate it whenever the base URL changes.
baseUrlInput.addEventListener('change', () => {
  cache.clear();
  loadVersions();
});

clearCacheButton.addEventListener('click', () => {
  cache.clear();
  const original = clearCacheButton.textContent;
  clearCacheButton.textContent = 'Cache cleared ✓';
  setTimeout(() => { clearCacheButton.textContent = original; }, 1500);
});

loadVersions();

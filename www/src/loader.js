/* Loading of the binary files, with in-memory caching and fetch stats. */
import { parseIndex } from './binary.js';
import { cacheGet, cacheGetOrLoad, cacheKey } from './cache.js';
import { fetchGunzipped } from './fetch.js';
import { formatBytes } from './format.js';
import { indexFile, batchFile, dataUrl } from './paths.js';
import { setProgressText } from './progress.js';

let bytesFetched = 0;
let filesFetched = 0;
let cacheHits = 0;

export function resetFetchStats() {
  bytesFetched = 0;
  filesFetched = 0;
  cacheHits = 0;
}

export function fetchStats() {
  return { bytesFetched, filesFetched, cacheHits };
}

export async function loadIndex(version, side) {
  const key = cacheKey(version, 'index', side);
  const cached = cacheGet(key);
  if (cached) {
    cacheHits += 1;
    return cached;
  }
  const file = indexFile(side);
  return cacheGetOrLoad(key, async () => {
    const bytes = await fetchGunzipped(dataUrl(`${version}/${file}`), (received, total) => {
      setProgressText(`Fetching ${file}… ${formatBytes(received)}${total ? ` / ${formatBytes(total)}` : ''}`);
    });
    bytesFetched += bytes.length;
    filesFetched += 1;
    return parseIndex(bytes);
  });
}

export async function loadBatch(version, chunk) {
  const key = cacheKey(version, 'batch', chunk);
  const cached = cacheGet(key);
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

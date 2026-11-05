import { decodeRecord, readMatchList, searchEntries, sidesFromMask } from './binary.js';
import { form, lookupButton, matchModeSelect, queryInput, resultsMeta, resultsSection, versionSelect } from './dom.js';
import { formatBytes } from './format.js';
import { fetchStats, loadBatch, loadIndex, resetFetchStats } from './loader.js';
import { batchFile, indexFile } from './paths.js';
import { hideError, hideProgress, showError, showProgress } from './progress.js';
import { renderResults } from './render.js';

function currentSide() {
  return form.elements.side.value;
}

export async function lookup() {
  hideError();
  const side = currentSide();
  const version = versionSelect.value;
  const query = queryInput.value.trim();
  if (!version || !query) return;

  const mode = matchModeSelect.value;
  resetFetchStats();
  lookupButton.disabled = true;
  const started = performance.now();

  // Phase 1: index for the selected side only.
  showProgress(1, null, `Fetching ${indexFile(side)}…`);
  try {
    const index = await loadIndex(version, side);
    const matches = searchEntries(index.entries, query, mode);
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

    // Phase 3: decode all matching records (entirely local).
    const sides = sidesFromMask(index.mask);
    const rows = [];
    for (const match of matches) {
      const data = batches.get(match.chunk);
      for (const recordOffset of readMatchList(data, match.offset)) {
        rows.push(decodeRecord(data, recordOffset, sides));
      }
    }

    const stats = fetchStats();
    hideProgress();
    renderResults(rows, { side, version, query, mode });
    const elapsed = Math.round(performance.now() - started);
    const parts = [`${stats.filesFetched} ${stats.filesFetched === 1 ? 'file' : 'files'} fetched (${formatBytes(stats.bytesFetched)} over the wire)`];
    if (stats.cacheHits) parts.push(`${stats.cacheHits} served from memory`);
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

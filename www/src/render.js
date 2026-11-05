import { SIDE_ORDER } from './constants.js';
import { resultsBody, resultsSection, resultsSummary, resultsTable } from './dom.js';

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

export function renderResults(rows, { side, version, query, mode }) {
  resultsSection.hidden = false;
  resultsTable.dataset.activeSide = side;
  resultsSummary.textContent = `Results (${rows.length})`;
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

/* Static viewer for the packed binary mapping data. See binary.js for the format. */
import '@picocss/pico/css/pico.min.css';
import './style.css';

import { clearCache } from './cache.js';
import { baseUrlInput, clearCacheButton, form } from './dom.js';
import { lookup } from './lookup.js';
import { loadVersions } from './versions.js';

form.addEventListener('submit', (event) => {
  event.preventDefault();
  lookup();
});

// versions.json is tiny — revalidate it whenever the base URL changes.
baseUrlInput.addEventListener('change', () => {
  clearCache();
  loadVersions();
});

clearCacheButton.addEventListener('click', () => {
  clearCache();
  const original = clearCacheButton.textContent;
  clearCacheButton.textContent = 'Cache cleared ✓';
  setTimeout(() => { clearCacheButton.textContent = original; }, 1500);
});

loadVersions();

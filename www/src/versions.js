import { versionSelect } from './dom.js';
import { dataUrl } from './paths.js';
import { hideError, hideProgress, showError, showProgress } from './progress.js';

export async function loadVersions() {
  const previous = versionSelect.value;
  versionSelect.disabled = true;
  versionSelect.innerHTML = '<option>Loading…</option>';
  showProgress(1, null, 'Fetching versions.json…');
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

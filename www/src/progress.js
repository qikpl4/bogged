import { errorBox, progressArea, progressEl, progressText } from './dom.js';

export function showProgress(max, value, text) {
  progressArea.hidden = false;
  progressEl.max = max;
  if (value === null) {
    progressEl.removeAttribute('value'); // indeterminate
  } else {
    progressEl.value = value;
  }
  if (text !== undefined) progressText.textContent = text;
}

export function hideProgress() {
  progressArea.hidden = true;
}

export function setProgressText(text) {
  progressText.textContent = text;
}

export function showError(error) {
  errorBox.hidden = false;
  errorBox.textContent = error?.message ?? String(error);
}

export function hideError() {
  errorBox.hidden = true;
  errorBox.textContent = '';
}

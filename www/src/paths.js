import { baseUrlInput } from './dom.js';

export const indexFile = (side) => `index_${side}.bin.gz`;
export const batchFile = (chunk) => `batch_${String(chunk).padStart(3, '0')}.bin.gz`;

export function baseUrl() {
  return (baseUrlInput.value.trim() || 'data').replace(/\/+$/, '');
}

export function dataUrl(path) {
  return `${baseUrl()}/${path}`;
}

import pako from 'pako';

import { GZIP_MAGIC_0, GZIP_MAGIC_1 } from './constants.js';

export async function fetchBytes(url, onBytes) {
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

export function gunzip(bytes) {
  // Guard against servers that transparently decompress .gz responses.
  if (bytes.length >= 2 && bytes[0] === GZIP_MAGIC_0 && bytes[1] === GZIP_MAGIC_1) {
    return pako.ungzip(bytes);
  }
  return bytes;
}

export async function fetchGunzipped(url, onBytes) {
  const raw = await fetchBytes(url, onBytes);
  try {
    return gunzip(raw);
  } catch (error) {
    throw new Error(`Could not decompress ${url}\n${error.message ?? error}`);
  }
}

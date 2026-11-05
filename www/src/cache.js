import { baseUrl } from './paths.js';

const cache = new Map(); // key -> parsed index | decompressed batch bytes | Promise thereof

export function cacheKey(...parts) {
  return [baseUrl(), ...parts].join('|');
}

export function cacheGet(key) {
  return cache.get(key);
}

export function cacheGetOrLoad(key, loader) {
  if (!cache.has(key)) {
    cache.set(key, loader().catch((error) => {
      cache.delete(key); // don't cache failures
      throw error;
    }));
  }
  return cache.get(key);
}

export function clearCache() {
  cache.clear();
}

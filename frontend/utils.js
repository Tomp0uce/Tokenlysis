// ===== API response helpers =====

export function extractItems(json) {
  // Normalise `/api/markets/top` payloads into a flat array for rendering.
  if (Array.isArray(json)) {
    return json;
  }
  if (json && Array.isArray(json.items)) {
    return json.items;
  }
  throw new Error("Invalid schema: missing 'items'");
}

export function resolveVersion(apiVersion, localVersion) {
  // Prefer API version strings but fall back to baked-in build metadata.
  if (apiVersion && apiVersion !== 'dev') return apiVersion;
  if (localVersion) return localVersion;
  return 'dev';
}

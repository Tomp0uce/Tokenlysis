export function extractItems(json) {
  if (Array.isArray(json)) {
    return json;
  }
  if (json && Array.isArray(json.items)) {
    return json.items;
  }
  throw new Error("Invalid schema: missing 'items'");
}

export function resolveVersion(apiVersion, localVersion) {
  if (apiVersion && apiVersion !== 'dev') return apiVersion;
  if (localVersion) return localVersion;
  return 'dev';
}

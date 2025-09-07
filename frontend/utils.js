export function extractItems(json) {
  if (Array.isArray(json)) {
    return json;
  }
  if (json && Array.isArray(json.items)) {
    return json.items;
  }
  throw new Error("Invalid schema: missing 'items'");
}

export function formatDiag(lastRequest, data) {
  const plan = data?.plan ?? 'unknown';
  const granularity = data?.granularity ?? 'unknown';
  const lastEtlItems = data?.last_etl_items ?? 'unknown';
  return `URL: ${lastRequest.url || ''} (${lastRequest.status || ''} in ${lastRequest.latency || 0}ms) | plan=${plan} | granularity=${granularity} | last_etl_items=${lastEtlItems}`;
}

export function formatMeta(marketMeta = {}, diagMeta = {}) {
  const plan = diagMeta.plan ?? 'unknown';
  const lastRefresh = marketMeta.last_refresh_at
    ? new Date(marketMeta.last_refresh_at).toISOString().slice(11, 16) + 'Z'
    : 'unknown';
  const source = marketMeta.data_source ?? 'unknown';
  const items = diagMeta.last_etl_items ?? 'unknown';
  const base = `Plan: ${plan} | Last refresh: ${lastRefresh} | Source: ${source} | Items: ${items}`;
  return marketMeta.stale ? `${base} <span class="badge">stale</span>` : base;
}

export function resolveVersion(apiVersion, localVersion) {
  if (apiVersion && apiVersion !== 'dev') return apiVersion;
  if (localVersion) return localVersion;
  return 'dev';
}

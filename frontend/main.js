import { getAppVersion } from './version.js';
import { extractItems, formatDiag, formatMeta, resolveVersion } from './utils.js';

const API_URL = document.querySelector('meta[name="api-url"]')?.content || '';
let lastRequest = {};
let marketMeta = {};
let diagMeta = null;
let backendLast = {};
let appVersion = 'unknown';

function formatPrice(p) {
  if (p === null || p === undefined) return '';
  if (p >= 1) return p.toFixed(2);
  if (p >= 0.01) return p.toFixed(4);
  return p.toFixed(6);
}

function formatNumber(n) {
  if (n === null || n === undefined) return '';
  return Number(n).toLocaleString('en-US');
}

function formatPct(p) {
  if (p === null || p === undefined) return '';
  return `${p.toFixed(2)}%`;
}

export async function loadLastRefresh() {
  const el = document.getElementById('last-update');
  if (!el) return;
  try {
    const res = await fetch(`${API_URL}/last-refresh`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    const ts = data.last_refresh_at;
    el.textContent = ts
      ? `Dernière mise à jour : ${ts}`
      : 'Dernière mise à jour : inconnue';
  } catch (err) {
    el.textContent = 'Dernière mise à jour : inconnue';
    console.error(err);
  }
}

export async function loadCryptos() {
  const statusEl = document.getElementById('status');
  statusEl.textContent = 'Loading...';
  document.getElementById('cryptos').style.display = 'none';
  const tbody = document.querySelector('#cryptos tbody');
  tbody.innerHTML = '';
  const url = `${API_URL}/markets/top?limit=20&vs=usd`;
  const start = performance.now();
  try {
    const res = await fetch(url);
    const latency = Math.round(performance.now() - start);
    lastRequest = { url, status: res.status, latency };
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    const items = extractItems(json);
    marketMeta = {
      last_refresh_at: json.last_refresh_at,
      stale: json.stale,
      data_source: json.data_source,
    };
    items.forEach((item) => {
      const tr = document.createElement('tr');
      tr.innerHTML = `<td>${item.coin_id}</td><td>${item.rank ?? ''}</td><td>${formatPrice(item.price)}</td><td>${formatNumber(item.market_cap)}</td><td>${formatNumber(item.volume_24h)}</td><td>${formatPct(item.pct_change_24h)}</td>`;
      tbody.appendChild(tr);
    });
    document.getElementById('cryptos').style.display = 'table';
    statusEl.textContent = '';
    document.getElementById('demo-banner').style.display = 'block';
  } catch (err) {
    statusEl.innerHTML = `Error fetching data <button id="retry">Retry</button>`;
    document.getElementById('retry').onclick = loadCryptos;
    console.error(err);
  }
  renderMeta();
  renderDebug();
  await loadDiag();
  await loadLastRefresh();
}

export async function loadVersion() {
  const el = document.getElementById('version');
  const local = getAppVersion();
  try {
    const res = await fetch(`${API_URL}/version`);
    if (res.ok) {
      const data = await res.json();
      appVersion = resolveVersion(data.version, local);
      el.textContent = `Version: ${appVersion}`;
      renderDebug();
      return;
    }
  } catch (err) {
    console.error(err);
  }
  appVersion = resolveVersion(null, local);
  el.textContent = `Version: ${appVersion}`;
  renderDebug();
}

export async function loadDiag() {
  try {
    const [diagRes, lastRes] = await Promise.all([
      fetch(`${API_URL}/diag`),
      fetch(`${API_URL}/debug/last-request`).catch(() => null),
    ]);
    if (!diagRes.ok) throw new Error(`HTTP ${diagRes.status}`);
    const data = await diagRes.json();
    diagMeta = data;
    backendLast = lastRes && lastRes.ok ? await lastRes.json() : {};
    document.getElementById('diag').textContent = formatDiag(lastRequest, data);
    renderMeta();
    renderDebug();
  } catch (err) {
    diagMeta = null;
    backendLast = {};
    document.getElementById('diag').textContent = formatDiag(lastRequest, null);
    renderMeta();
    renderDebug();
    console.error(err);
  }
}

export function renderMeta() {
  const el = document.getElementById('meta');
  el.innerHTML = formatMeta(marketMeta, diagMeta ?? {});
}

function renderDebug() {
  const el = document.getElementById('debug-panel');
  if (!el) return;
  const plan = diagMeta?.plan || 'unknown';
  const base = diagMeta?.base_url || '';
  const lastRefresh = marketMeta.last_refresh_at || '';
  const source = marketMeta.data_source || '';
  el.textContent = `version=${appVersion} plan=${plan} base=${base} last_refresh_at=${lastRefresh} source=${source} last_request=${backendLast.endpoint || ''} status=${backendLast.status || ''}`;
}

export function init() {
  loadVersion();
  loadCryptos();
  setInterval(loadLastRefresh, 60000);
}

if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', init);
}

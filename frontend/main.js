import { getAppVersion } from './version.js';
import { extractItems, formatDiag, formatMeta, resolveVersion } from './utils.js';

const API_URL = document.querySelector('meta[name="api-url"]')?.content || '';
let lastRequest = {};
let marketMeta = {};
let diagMeta = null;

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
  await loadDiag();
}

export async function loadVersion() {
  const el = document.getElementById('version');
  const local = getAppVersion();
  try {
    const res = await fetch(`${API_URL}/version`);
    if (res.ok) {
      const data = await res.json();
      el.textContent = `Version: ${resolveVersion(data.version, local)}`;
      return;
    }
  } catch (err) {
    console.error(err);
  }
  el.textContent = `Version: ${resolveVersion(null, local)}`;
}

export async function loadDiag() {
  try {
    const res = await fetch(`${API_URL}/diag`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    diagMeta = data;
    document.getElementById('diag').textContent = formatDiag(lastRequest, data);
    renderMeta();
  } catch (err) {
    diagMeta = null;
    document.getElementById('diag').textContent = formatDiag(lastRequest, null);
    renderMeta();
    console.error(err);
  }
}

export function renderMeta() {
  const el = document.getElementById('meta');
  el.innerHTML = formatMeta(marketMeta, diagMeta ?? {});
}

export function init() {
  loadVersion();
  loadCryptos();
}

if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', init);
}

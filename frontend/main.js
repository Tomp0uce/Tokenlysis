import { getAppVersion } from './version.js';
import { extractItems, resolveVersion } from './utils.js';

const API_URL = document.querySelector('meta[name="api-url"]')?.content || '';
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

export async function loadCryptos() {
  const statusEl = document.getElementById('status');
  statusEl.textContent = 'Loading...';
  document.getElementById('cryptos').style.display = 'none';
  const tbody = document.querySelector('#cryptos tbody');
  tbody.innerHTML = '';
  const url = `${API_URL}/markets/top?limit=20&vs=usd`;
  try {
    const res = await fetch(url);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const json = await res.json();
    const items = extractItems(json);
    const lastEl = document.getElementById('last-update');
    lastEl.textContent = json.last_refresh_at
      ? `Dernière mise à jour : ${json.last_refresh_at} (source: ${json.data_source || 'unknown'})`
      : 'Dernière mise à jour : inconnue';
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
      return;
    }
  } catch (err) {
    console.error(err);
  }
  appVersion = resolveVersion(null, local);
  el.textContent = `Version: ${appVersion}`;
}

export function init() {
  loadVersion();
  loadCryptos();
}

if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', init);
}

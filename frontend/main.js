import { getAppVersion } from './version.js';
import { extractItems, resolveVersion } from './utils.js';

// ===== Application state & configuration =====
const API_URL = document.querySelector('meta[name="api-url"]')?.content || '';
let appVersion = 'unknown';
export const selectedCategories = [];

const SORTABLE_COLUMN_ACCESSORS = new Map([
  [2, (item) => item.rank],
  [3, (item) => item.price],
  [4, (item) => item.market_cap],
  [5, (item) => item.fully_diluted_market_cap],
  [6, (item) => item.volume_24h],
  [7, (item) => item.pct_change_24h],
  [8, (item) => item.pct_change_7d],
  [9, (item) => item.pct_change_30d],
]);

let marketItems = [];
const boundSortableHeaders = new WeakSet();
let sortState = { columnIndex: null, direction: 'asc' };

// ===== Formatting helpers =====
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
  if (typeof p !== 'number' || Number.isNaN(p) || !Number.isFinite(p)) return '';
  return `${p.toFixed(2)}%`;
}

function changeClass(value) {
  if (value === null || value === undefined) {
    return 'change-cell';
  }
  if (value > 0) return 'change-cell change-positive';
  if (value < 0) return 'change-cell change-negative';
  return 'change-cell';
}

function renderChangeCell(value) {
  return `<td class="${changeClass(value)}">${formatPct(value)}</td>`;
}

function normalizeNumericValue(value) {
  if (value === null || value === undefined) return null;
  const num = Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) return null;
  return num;
}

function compareNumericValues(a, b, direction) {
  const aVal = normalizeNumericValue(a);
  const bVal = normalizeNumericValue(b);
  if (aVal === null && bVal === null) return 0;
  if (aVal === null) return 1;
  if (bVal === null) return -1;
  if (direction === 'asc') return aVal - bVal;
  return bVal - aVal;
}

function renderRows(items) {
  const tbody = document.querySelector('#cryptos tbody');
  if (!tbody) return;
  tbody.innerHTML = '';
  const fragment = document.createDocumentFragment();
  items.forEach((item) => {
    const tr = document.createElement('tr');
    const cats = item.category_names || [];
    let badges = '';
    cats.slice(0, 3).forEach((name) => {
      badges += `<span class="badge" title="${name}">${name}</span> `;
    });
    if (cats.length > 3) {
      const extra = cats.slice(3).join(', ');
      badges += `<span class="badge" title="${extra}">+${cats.length - 3}</span>`;
    }
    tr.innerHTML = `<td>${item.coin_id}</td><td>${badges.trim()}</td><td>${item.rank ?? ''}</td><td>${formatPrice(item.price)}</td><td>${formatNumber(item.market_cap)}</td><td>${formatNumber(item.fully_diluted_market_cap)}</td><td>${formatNumber(item.volume_24h)}</td>${renderChangeCell(item.pct_change_24h)}${renderChangeCell(item.pct_change_7d)}${renderChangeCell(item.pct_change_30d)}`;
    fragment.appendChild(tr);
  });
  tbody.appendChild(fragment);
}

// ===== Sorting helpers =====
function clearSortIndicators() {
  document.querySelectorAll('#cryptos thead th').forEach((th) => {
    th.classList.remove('sort-asc', 'sort-desc');
  });
}

function applySortIndicators(columnIndex, direction) {
  clearSortIndicators();
  const headers = document.querySelectorAll('#cryptos thead th');
  const target = headers[columnIndex];
  if (target) {
    target.classList.add(direction === 'asc' ? 'sort-asc' : 'sort-desc');
  }
}

function renderSortedItems() {
  const hasSort =
    sortState.columnIndex !== null && SORTABLE_COLUMN_ACCESSORS.has(sortState.columnIndex);
  const itemsToRender = [...marketItems];
  if (hasSort) {
    const accessor = SORTABLE_COLUMN_ACCESSORS.get(sortState.columnIndex);
    itemsToRender.sort((a, b) =>
      compareNumericValues(accessor?.(a), accessor?.(b), sortState.direction)
    );
    applySortIndicators(sortState.columnIndex, sortState.direction);
  } else {
    clearSortIndicators();
  }
  renderRows(itemsToRender);
}

function initializeSorting() {
  const headers = document.querySelectorAll('#cryptos thead th');
  headers.forEach((th, index) => {
    if (!SORTABLE_COLUMN_ACCESSORS.has(index) || boundSortableHeaders.has(th)) {
      return;
    }
    th.classList.add('sortable');
    th.addEventListener('click', () => {
      const direction =
        sortState.columnIndex === index && sortState.direction === 'asc'
          ? 'desc'
          : 'asc';
      sortState = { columnIndex: index, direction };
      if (marketItems.length) {
        renderSortedItems();
      }
    });
    boundSortableHeaders.add(th);
  });
}

export async function loadCryptos() {
  const statusEl = document.getElementById('status');
  statusEl.textContent = 'Loading...';
  document.getElementById('cryptos').style.display = 'none';
  const tbody = document.querySelector('#cryptos tbody');
  tbody.innerHTML = '';
  initializeSorting();
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
    marketItems = [...items];
    renderSortedItems();
    document.getElementById('cryptos').style.display = 'table';
    statusEl.textContent = '';
    try {
      const diag = await fetch(`${API_URL}/diag`).then(r => (r.ok ? r.json() : null));
      if (diag?.plan === 'demo') {
        document.getElementById('demo-banner').style.display = 'block';
      }
    } catch {}
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

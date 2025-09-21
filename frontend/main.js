import { getAppVersion } from './version.js';
import { extractItems, resolveVersion } from './utils.js';
import {
  createAreaChart,
  refreshChartsTheme,
  formatCompactUsd,
  createRadialGauge,
  updateRadialGauge,
} from './charting.js';
import { initThemeToggle, onThemeChange } from './theme.js';
import { calculateAvailableRanges, pickInitialRange, syncRangeSelector } from './range.js';

const API_URL = document.querySelector('meta[name="api-url"]')?.content || '';
const API_BASE = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL;
const MARKET_OVERVIEW_LIMIT = 6;
const MARKET_PREFERRED_RANGE = '1m';
const MAX_RANGE_KEY = 'max';
const RANGE_DESCRIPTIONS = new Map([
  ['24h', 'les dernières 24 heures'],
  ['7d', 'les 7 derniers jours'],
  ['1m', 'le dernier mois'],
  ['3m', 'les 3 derniers mois'],
  ['1y', 'la dernière année'],
  ['2y', 'les 2 dernières années'],
  ['5y', 'les 5 dernières années'],
  [MAX_RANGE_KEY, "l'ensemble de l'historique disponible"],
]);
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
let sortState = { columnIndex: 2, direction: 'asc' };
let marketOverviewChart = null;
let marketOverviewRange = null;
let marketOverviewCoinIds = [];
let marketOverviewSnapshot = null;
const marketHistoryCache = new Map();
let marketRangeAvailability = new Set();
let marketRangeListenersBound = false;
let fearGreedChart = null;

// ===== formatting helpers =====
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

function applyChangeValue(element, value) {
  if (!element) {
    return;
  }
  element.classList.remove('change-positive', 'change-negative');
  const numeric = normalizeNumericValue(value);
  if (numeric === null) {
    element.textContent = '—';
    return;
  }
  element.textContent = formatPct(numeric);
  if (numeric > 0) {
    element.classList.add('change-positive');
  } else if (numeric < 0) {
    element.classList.add('change-negative');
  }
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

function weightedAverage(items, weightSelector, valueSelector) {
  if (!Array.isArray(items) || typeof weightSelector !== 'function' || typeof valueSelector !== 'function') {
    return null;
  }
  let weightedSum = 0;
  let weightTotal = 0;
  items.forEach((item) => {
    const weight = normalizeNumericValue(weightSelector(item));
    const value = normalizeNumericValue(valueSelector(item));
    if (weight === null || value === null) {
      return;
    }
    weightedSum += weight * value;
    weightTotal += weight;
  });
  if (weightTotal === 0) {
    return null;
  }
  return weightedSum / weightTotal;
}

export function computeTopMarketCapSeries(items, limit = 5) {
  const normalized = (items || [])
    .map((item) => ({
      id: item?.coin_id || '—',
      value: normalizeNumericValue(item?.market_cap),
    }))
    .filter((entry) => entry.value !== null)
    .sort((a, b) => b.value - a.value)
    .slice(0, limit);
  return {
    categories: normalized.map((entry) => entry.id),
    data: normalized.map((entry) => entry.value),
  };
}

function getMarketRangeContainer() {
  return document.getElementById('market-range-selector');
}

function setMarketRangeActive(range) {
  document.querySelectorAll('#market-range-selector [data-range]').forEach((button) => {
    const isActive = button.dataset.range === range;
    button.classList.toggle('active', isActive);
    button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
}

function describeRange(range) {
  return RANGE_DESCRIPTIONS.get(range) || 'la période sélectionnée';
}

function updateMarketRangeAvailability(categories = []) {
  marketRangeAvailability = calculateAvailableRanges(categories);
  const container = getMarketRangeContainer();
  if (container) {
    syncRangeSelector(container, marketRangeAvailability);
  }
  return marketRangeAvailability;
}

function updateMarketSubtitle(range, hasTimeline) {
  const subtitleEl = document.getElementById('market-overview-subtitle');
  if (!subtitleEl) {
    return;
  }
  if (!hasTimeline) {
    subtitleEl.textContent = 'Répartition instantanée des plus gros actifs.';
    return;
  }
  subtitleEl.textContent = `Capitalisation cumulée des leaders sur ${describeRange(range)}.`;
}

function resetMarketRangeState() {
  marketOverviewRange = null;
  marketRangeAvailability = new Set();
  marketHistoryCache.clear();
  setMarketRangeActive('');
  const container = getMarketRangeContainer();
  if (container) {
    syncRangeSelector(container, new Set());
  }
}

function pruneMarketRange(range) {
  if (!marketRangeAvailability.has(range)) {
    return;
  }
  marketRangeAvailability = new Set(
    Array.from(marketRangeAvailability.values()).filter((key) => key !== range),
  );
  const container = getMarketRangeContainer();
  if (container) {
    syncRangeSelector(container, marketRangeAvailability);
  }
}

function buildSnapshotSeries(snapshot) {
  const categories = Array.isArray(snapshot?.categories)
    ? snapshot.categories.map((label, index) => `${index + 1}. ${String(label || '').toUpperCase()}`)
    : [];
  return {
    categories,
    data: Array.isArray(snapshot?.data) ? snapshot.data : [],
  };
}

async function drawMarketOverview(container, range, aggregated, snapshot) {
  const snapshotSeries = buildSnapshotSeries(snapshot);
  const hasTimeline =
    Array.isArray(aggregated?.categories) &&
    aggregated.categories.length > 0 &&
    Array.isArray(aggregated?.data) &&
    aggregated.data.length > 0;
  const categories = hasTimeline ? aggregated.categories : snapshotSeries.categories;
  const data = hasTimeline ? aggregated.data : snapshotSeries.data;
  const xAxisType = hasTimeline ? 'datetime' : 'category';
  const rangeLabel = typeof range === 'string' && range ? range.toUpperCase() : '';
  const seriesName = hasTimeline ? `Capitalisation cumulée (${rangeLabel})` : 'Top capitalisations';
  updateMarketSubtitle(range, hasTimeline);
  if (!marketOverviewChart) {
    marketOverviewChart = await createAreaChart(container, {
      name: seriesName,
      categories,
      data,
      colorVar: '--chart-market',
      xAxisType,
    });
  } else {
    await marketOverviewChart.updateOptions(
      {
        xaxis: { categories, type: xAxisType },
      },
      false,
      true,
    );
    await marketOverviewChart.updateSeries(
      [
        {
          name: seriesName,
          data,
        },
      ],
      true,
    );
  }
  if (hasTimeline) {
    marketOverviewRange = range;
    setMarketRangeActive(range);
  } else {
    marketOverviewRange = null;
    setMarketRangeActive('');
  }
}

function buildHistoryUrl(coinId, range) {
  const safeId = encodeURIComponent(coinId);
  const safeRange = encodeURIComponent(range);
  const base = API_BASE;
  const prefix = base ? `${base}` : '';
  return `${prefix}/price/${safeId}/history?range=${safeRange}`;
}

export function combineMarketHistories(histories = []) {
  const totals = new Map();
  (histories || []).forEach((history) => {
    if (!Array.isArray(history)) {
      return;
    }
    history.forEach((point) => {
      const value = normalizeNumericValue(point?.market_cap);
      if (value === null) {
        return;
      }
      const rawTimestamp = point?.snapshot_at;
      if (typeof rawTimestamp !== 'string') {
        return;
      }
      const date = new Date(rawTimestamp);
      if (Number.isNaN(date.getTime())) {
        return;
      }
      const timeKey = date.getTime();
      const existing = totals.get(timeKey);
      if (existing) {
        existing.total += value;
      } else {
        totals.set(timeKey, { iso: date.toISOString(), total: value });
      }
    });
  });
  if (totals.size === 0) {
    return { categories: [], data: [] };
  }
  const sorted = Array.from(totals.entries()).sort((a, b) => a[0] - b[0]);
  return {
    categories: sorted.map(([, entry]) => entry.iso),
    data: sorted.map(([, entry]) => entry.total),
  };
}

export async function fetchAggregatedTopMarketHistory(
  coinIds = [],
  { range = MARKET_PREFERRED_RANGE, fetchImpl } = {},
) {
  const ids = Array.isArray(coinIds)
    ? coinIds.filter((id) => typeof id === 'string' && id.trim() && id !== '—')
    : [];
  if (ids.length === 0) {
    return { categories: [], data: [] };
  }
  const fetcher = typeof fetchImpl === 'function' ? fetchImpl : typeof fetch === 'function' ? fetch : null;
  if (!fetcher) {
    return { categories: [], data: [] };
  }
  const histories = await Promise.all(
    ids.map(async (coinId) => {
      const url = buildHistoryUrl(coinId, range);
      try {
        const response = await fetcher(url);
        if (!response?.ok) {
          return [];
        }
        const payload = await response.json();
        if (!payload || !Array.isArray(payload.points)) {
          return [];
        }
        return payload.points;
      } catch (error) {
        return [];
      }
    }),
  );
  return combineMarketHistories(histories);
}

async function getAggregatedHistory(range) {
  const key = typeof range === 'string' && range.trim() ? range : MAX_RANGE_KEY;
  if (marketHistoryCache.has(key)) {
    return marketHistoryCache.get(key);
  }
  const data = await fetchAggregatedTopMarketHistory(marketOverviewCoinIds, { range: key });
  marketHistoryCache.set(key, data);
  return data;
}

function updateSummary(items) {
  const totalMarketCap = items.reduce((acc, item) => acc + (normalizeNumericValue(item.market_cap) || 0), 0);
  const totalVolume = items.reduce((acc, item) => acc + (normalizeNumericValue(item.volume_24h) || 0), 0);
  const marketCapChange24h = weightedAverage(items, (item) => item.market_cap, (item) => item.pct_change_24h);
  const marketCapChange7d = weightedAverage(items, (item) => item.market_cap, (item) => item.pct_change_7d);
  const volumeChange24h = weightedAverage(items, (item) => item.volume_24h, (item) => item.pct_change_24h);
  const volumeChange7d = weightedAverage(items, (item) => item.volume_24h, (item) => item.pct_change_7d);
  const summaryMap = new Map([
    ['summary-market-cap', formatCompactUsd(totalMarketCap) || '—'],
    ['summary-volume', formatCompactUsd(totalVolume) || '—'],
  ]);
  summaryMap.forEach((value, id) => {
    const el = document.getElementById(id);
    if (el) {
      el.textContent = value;
    }
  });
  applyChangeValue(document.getElementById('summary-market-cap-change-24h'), marketCapChange24h);
  applyChangeValue(document.getElementById('summary-market-cap-change-7d'), marketCapChange7d);
  applyChangeValue(document.getElementById('summary-volume-change-24h'), volumeChange24h);
  applyChangeValue(document.getElementById('summary-volume-change-7d'), volumeChange7d);
}

async function renderMarketOverview(items) {
  const container = document.getElementById('market-overview-chart');
  if (!container) return;
  marketOverviewSnapshot = computeTopMarketCapSeries(items, MARKET_OVERVIEW_LIMIT);
  marketOverviewCoinIds = Array.isArray(marketOverviewSnapshot.categories)
    ? [...marketOverviewSnapshot.categories]
    : [];
  resetMarketRangeState();
  bindMarketRangeButtons();

  if (marketOverviewCoinIds.length === 0) {
    await drawMarketOverview(container, '', null, marketOverviewSnapshot);
    return;
  }

  try {
    const maxData = await fetchAggregatedTopMarketHistory(marketOverviewCoinIds, { range: MAX_RANGE_KEY });
    marketHistoryCache.set(MAX_RANGE_KEY, maxData);
    const availability = updateMarketRangeAvailability(maxData.categories);
    if (!availability.size) {
      await drawMarketOverview(container, '', null, marketOverviewSnapshot);
      return;
    }
    const initialRange = pickInitialRange(availability, MARKET_PREFERRED_RANGE) || MAX_RANGE_KEY;
    const initialData = initialRange === MAX_RANGE_KEY ? maxData : await getAggregatedHistory(initialRange);
    await drawMarketOverview(container, initialRange, initialData, marketOverviewSnapshot);
  } catch (error) {
    console.error(error);
    await drawMarketOverview(container, '', null, marketOverviewSnapshot);
  }
}

export async function loadFearGreedWidget({ fetchImpl } = {}) {
  const card = document.getElementById('fear-greed-card');
  const gaugeContainer = document.getElementById('fear-greed-gauge');
  const valueEl = document.getElementById('fear-greed-value');
  const classificationEl = document.getElementById('fear-greed-classification');
  if (!card || !gaugeContainer || !valueEl || !classificationEl) {
    return null;
  }
  const fetcher = typeof fetchImpl === 'function' ? fetchImpl : typeof fetch === 'function' ? fetch : null;
  if (!fetcher) {
    return null;
  }
  try {
    const response = await fetcher(`${API_URL}/fear-greed/latest`);
    if (!response?.ok) {
      throw new Error(`HTTP ${response?.status ?? 'error'}`);
    }
    const payload = await response.json();
    const rawValue = Number(payload?.value ?? 0);
    const value = Number.isFinite(rawValue) ? Math.round(rawValue) : 0;
    const classification = String(payload?.classification || '').trim() || 'Indéterminé';
    valueEl.textContent = String(value);
    classificationEl.textContent = classification;
    const gaugeData = { value, classification };
    if (!fearGreedChart) {
      fearGreedChart = await createRadialGauge(gaugeContainer, gaugeData);
    } else {
      await updateRadialGauge(fearGreedChart, gaugeData);
    }
    card.setAttribute('aria-label', `Indice Fear & Greed : ${classification} (${value}/100)`);
    if (!card.getAttribute('href')) {
      card.setAttribute('href', './fear-greed.html');
    }
    return fearGreedChart;
  } catch (error) {
    console.error(error);
    valueEl.textContent = '0';
    classificationEl.textContent = 'Indisponible';
    if (fearGreedChart) {
      await updateRadialGauge(fearGreedChart, { value: 0, classification: 'Indisponible' });
    }
    return null;
  }
}

function bindMarketRangeButtons() {
  if (marketRangeListenersBound) {
    return;
  }
  const container = getMarketRangeContainer();
  if (!container) {
    return;
  }
  container.querySelectorAll('[data-range]').forEach((button) => {
    button.addEventListener('click', async () => {
      const { range } = button.dataset;
      if (!range || button.disabled || !marketRangeAvailability.has(range) || range === marketOverviewRange) {
        return;
      }
      try {
        await loadMarketOverviewRange(range);
      } catch (error) {
        console.error(error);
      }
    });
  });
  marketRangeListenersBound = true;
}

async function loadMarketOverviewRange(range) {
  if (!marketOverviewCoinIds.length) {
    return;
  }
  if (!marketRangeAvailability.has(range)) {
    return;
  }
  const container = document.getElementById('market-overview-chart');
  if (!container) {
    return;
  }
  try {
    const data = await getAggregatedHistory(range);
    const hasTimeline =
      Array.isArray(data?.categories) &&
      data.categories.length > 0 &&
      Array.isArray(data?.data) &&
      data.data.length > 0;
    if (!hasTimeline && range !== MAX_RANGE_KEY) {
      pruneMarketRange(range);
      const fallback = pickInitialRange(marketRangeAvailability, MARKET_PREFERRED_RANGE);
      if (fallback && fallback !== range) {
        await loadMarketOverviewRange(fallback);
        return;
      }
    }
    await drawMarketOverview(container, range, data, marketOverviewSnapshot);
  } catch (error) {
    console.error(error);
  }
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
    const coinId = item.coin_id ?? '';
    tr.innerHTML = `<td data-label="Actif">${coinId}</td><td data-label="Catégories">${badges.trim()}</td><td data-label="Rank">${item.rank ?? ''}</td><td data-label="Prix">${formatPrice(item.price)}</td><td data-label="Market Cap">${formatNumber(item.market_cap)}</td><td data-label="FDV">${formatNumber(item.fully_diluted_market_cap)}</td><td data-label="Volume 24h">${formatNumber(item.volume_24h)}</td>${renderChangeCell(item.pct_change_24h)}${renderChangeCell(item.pct_change_7d)}${renderChangeCell(item.pct_change_30d)}`;
    const actionCell = document.createElement('td');
    actionCell.setAttribute('data-label', 'Détails');
    if (coinId) {
      const link = document.createElement('a');
      link.className = 'details-link';
      link.textContent = 'Détails';
      link.href = `./coin.html?coin_id=${encodeURIComponent(coinId)}`;
      link.setAttribute('aria-label', `Voir les détails pour ${coinId}`);
      actionCell.appendChild(link);
    } else {
      actionCell.textContent = '—';
    }
    tr.appendChild(actionCell);
    fragment.appendChild(tr);
  });
  tbody.appendChild(fragment);
}

// ===== sorting helpers =====
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
      compareNumericValues(accessor?.(a), accessor?.(b), sortState.direction),
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
  statusEl.textContent = 'Chargement...';
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
    updateSummary(marketItems);
    await renderMarketOverview(marketItems);
    renderSortedItems();
    document.getElementById('cryptos').style.display = 'table';
    statusEl.textContent = '';
    try {
      const diag = await fetch(`${API_URL}/diag`).then((r) => (r.ok ? r.json() : null));
      if (diag?.plan === 'demo') {
        document.getElementById('demo-banner').style.display = 'block';
      }
    } catch {}
  } catch (err) {
    statusEl.innerHTML = `Erreur lors de la récupération des données <button id="retry">Réessayer</button>`;
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

export async function init() {
  initThemeToggle('[data-theme-toggle]');
  onThemeChange((theme) => {
    refreshChartsTheme(theme);
  });
  loadVersion();
  await loadCryptos();
  try {
    await loadFearGreedWidget();
  } catch (error) {
    console.error(error);
  }
}

if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', () => {
    init().catch((error) => console.error(error));
  });
}

export const __test__ = {
  computeTopMarketCapSeries,
  combineMarketHistories,
  fetchAggregatedTopMarketHistory,
  loadFearGreedWidget,
};

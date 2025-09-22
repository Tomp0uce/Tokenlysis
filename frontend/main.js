import { getAppVersion } from './version.js';
import { resolveVersion } from './utils.js';
import {
  createAreaChart,
  refreshChartsTheme,
  formatCompactUsd,
  createRadialGauge,
  updateRadialGauge,
} from './charting.js';
import { initThemeToggle, onThemeChange } from './theme.js';
import { calculateAvailableRanges, pickInitialRange, syncRangeSelector } from './range.js';
import {
  computeSentimentSnapshots,
  collectSnapshotElements,
  renderSentimentSnapshots,
} from './sentiment.js';

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

const COINGECKO_BASE_URL = 'https://api.coingecko.com/api/v3';
const COINGECKO_MARKETS_ENDPOINT = `${COINGECKO_BASE_URL}/coins/markets`;
const COINGECKO_DEFAULT_LIMIT = 1000;
const COINGECKO_MAX_PER_PAGE = 250;
const DEFAULT_ROWS_PER_PAGE = 20;

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

const DATA_LABELS = {
  asset: 'Actif',
  categories: 'Catégories',
  rank: 'Rank',
  price: 'Prix ($)',
  marketCap: 'Market Cap',
  fullyDiluted: 'Fully Diluted Market Cap',
  volume: 'Volume 24h',
  change24h: 'Change 24h',
  change7d: 'Change 7j',
  change30d: 'Change 30j',
  details: 'Détails',
};

let marketItems = [];
let paginationState = { page: 1, perPage: DEFAULT_ROWS_PER_PAGE };
let paginationElements = null;
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
let widgetSnapshotElements = null;
let widgetLatestDatapoint = null;
let widgetHistoryPoints = [];

// ===== formatting helpers =====
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

function renderChangeCell(value, label) {
  const labelAttr = typeof label === 'string' && label.trim() ? ` data-label="${label}"` : '';
  return `<td class="${changeClass(value)}"${labelAttr}>${formatPct(value)}</td>`;
}

function formatDisplayName(item) {
  const rawName = typeof item?.name === 'string' ? item.name.trim() : '';
  if (rawName) {
    const first = rawName.charAt(0);
    if (first && first === first.toUpperCase()) {
      return rawName;
    }
    return `${first.toUpperCase()}${rawName.slice(1)}`;
  }
  const fallbackSlug = typeof item?.coin_id === 'string' ? item.coin_id.trim() : '';
  if (!fallbackSlug) {
    return '—';
  }
  const fallback = fallbackSlug.replace(/[-_]+/g, ' ').replace(/\s{2,}/g, ' ').trim();
  if (!fallback) {
    return '—';
  }
  const first = fallback.charAt(0);
  return `${first.toUpperCase()}${fallback.slice(1)}`;
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

function pickFirstValidNumber(...values) {
  for (const value of values) {
    const numeric = normalizeNumericValue(value);
    if (numeric !== null) {
      return numeric;
    }
  }
  return null;
}

function mapCoinGeckoItem(raw, fallbackRank) {
  const safeObject = raw && typeof raw === 'object' ? raw : {};
  const categories = Array.isArray(safeObject.categories)
    ? safeObject.categories
        .map((item) => (typeof item === 'string' ? item.trim() : ''))
        .filter((item) => item)
    : [];
  const rankValue = normalizeNumericValue(safeObject.market_cap_rank);
  return {
    coin_id: typeof safeObject.id === 'string' ? safeObject.id : '',
    name: typeof safeObject.name === 'string' ? safeObject.name : '',
    symbol: typeof safeObject.symbol === 'string' ? safeObject.symbol : '',
    logo_url: typeof safeObject.image === 'string' ? safeObject.image : '',
    rank: rankValue !== null ? rankValue : fallbackRank,
    price: normalizeNumericValue(safeObject.current_price),
    market_cap: normalizeNumericValue(safeObject.market_cap),
    fully_diluted_market_cap: normalizeNumericValue(safeObject.fully_diluted_valuation),
    volume_24h: normalizeNumericValue(safeObject.total_volume),
    pct_change_24h: pickFirstValidNumber(
      safeObject.price_change_percentage_24h,
      safeObject.price_change_percentage_24h_in_currency,
    ),
    pct_change_7d: pickFirstValidNumber(
      safeObject.price_change_percentage_7d_in_currency,
      safeObject.price_change_percentage_7d,
    ),
    pct_change_30d: pickFirstValidNumber(
      safeObject.price_change_percentage_30d_in_currency,
      safeObject.price_change_percentage_30d,
    ),
    category_names: categories,
  };
}

function mapCoinGeckoItems(items) {
  if (!Array.isArray(items)) {
    return [];
  }
  return items.map((item, index) => mapCoinGeckoItem(item, index + 1));
}

async function fetchCoinGeckoMarkets({
  limit = COINGECKO_DEFAULT_LIMIT,
  perPage = COINGECKO_MAX_PER_PAGE,
  vs = 'usd',
  fetchImpl,
} = {}) {
  const fetcher = typeof fetchImpl === 'function' ? fetchImpl : typeof fetch === 'function' ? fetch : null;
  if (!fetcher) {
    throw new Error('fetch is not available in this environment');
  }
  const requestedLimit = Math.max(1, Number(limit) || COINGECKO_DEFAULT_LIMIT);
  const pageSize = Math.max(1, Math.min(Number(perPage) || COINGECKO_MAX_PER_PAGE, COINGECKO_MAX_PER_PAGE));
  const totalPages = Math.ceil(requestedLimit / pageSize);
  const aggregated = [];
  for (let page = 1; page <= totalPages; page += 1) {
    const url = new URL(COINGECKO_MARKETS_ENDPOINT);
    url.searchParams.set('vs_currency', vs);
    url.searchParams.set('order', 'market_cap_desc');
    url.searchParams.set('per_page', String(pageSize));
    url.searchParams.set('page', String(page));
    url.searchParams.set('sparkline', 'false');
    url.searchParams.set('price_change_percentage', '24h,7d,30d');
    const response = await fetcher(url.toString());
    if (!response?.ok) {
      throw new Error(`CoinGecko request failed with status ${response?.status ?? 'unknown'}`);
    }
    const data = await response.json();
    if (!Array.isArray(data)) {
      throw new Error('Invalid CoinGecko response schema');
    }
    aggregated.push(...data);
    if (aggregated.length >= requestedLimit) {
      break;
    }
    if (data.length < pageSize) {
      break;
    }
  }
  return aggregated.slice(0, requestedLimit);
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

function updateWidgetSnapshots() {
  if (!widgetSnapshotElements) {
    widgetSnapshotElements = collectSnapshotElements();
  }
  if (!widgetSnapshotElements || widgetSnapshotElements.size === 0) {
    return;
  }
  const snapshots = computeSentimentSnapshots(widgetLatestDatapoint, widgetHistoryPoints);
  renderSentimentSnapshots(widgetSnapshotElements, snapshots);
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
  updateWidgetSnapshots();
  try {
    const response = await fetcher(`${API_URL}/fng/latest`);
    if (!response?.ok) {
      throw new Error(`HTTP ${response?.status ?? 'error'}`);
    }
    const payload = await response.json();
    const rawScore = Number(payload?.score ?? payload?.value ?? 0);
    const value = Number.isFinite(rawScore) ? Math.round(rawScore) : 0;
    const classification = String(payload?.label || payload?.classification || '').trim() || 'Indéterminé';
    const timestamp = typeof payload?.timestamp === 'string' ? payload.timestamp : new Date().toISOString();
    valueEl.textContent = String(value);
    classificationEl.textContent = classification;
    widgetLatestDatapoint = { timestamp, value, classification };
    updateWidgetSnapshots();
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
    try {
      const historyResponse = await fetcher(`${API_URL}/fng/history?days=90`);
      if (!historyResponse?.ok) {
        throw new Error(`HTTP ${historyResponse?.status ?? 'error'}`);
      }
      const historyPayload = await historyResponse.json();
      const rawPoints = Array.isArray(historyPayload?.points) ? historyPayload.points : [];
      widgetHistoryPoints = rawPoints
        .map((point) => {
          const timestamp = typeof point?.timestamp === 'string' ? point.timestamp : null;
          const score = Number(point?.score ?? point?.value ?? 0);
          const numeric = Number.isFinite(score) ? Math.round(score) : 0;
          const label = String(point?.label || point?.classification || '').trim() || 'Indéterminé';
          return timestamp ? { timestamp, value: numeric, classification: label } : null;
        })
        .filter((point) => point);
      updateWidgetSnapshots();
    } catch (historyError) {
      console.error(historyError);
      widgetHistoryPoints = [];
      updateWidgetSnapshots();
    }
    return fearGreedChart;
  } catch (error) {
    console.error(error);
    valueEl.textContent = '0';
    classificationEl.textContent = 'Indisponible';
    widgetLatestDatapoint = null;
    widgetHistoryPoints = [];
    updateWidgetSnapshots();
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

function formatCurrencyCell(value) {
  const formatted = formatCompactUsd(value);
  if (typeof formatted === 'string' && formatted.trim()) {
    return formatted;
  }
  return '—';
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
    const displayName = formatDisplayName(item);
    const priceDisplay = formatCurrencyCell(item.price);
    const marketCapDisplay = formatCurrencyCell(item.market_cap);
    const fdvDisplay = formatCurrencyCell(item.fully_diluted_market_cap);
    const volumeDisplay = formatCurrencyCell(item.volume_24h);
    tr.innerHTML = `<td data-label="${DATA_LABELS.asset}"></td>`
      + `<td data-label="${DATA_LABELS.categories}">${badges.trim()}</td>`
      + `<td data-label="${DATA_LABELS.rank}">${item.rank ?? ''}</td>`
      + `<td data-label="${DATA_LABELS.price}">${priceDisplay}</td>`
      + `<td data-label="${DATA_LABELS.marketCap}">${marketCapDisplay}</td>`
      + `<td data-label="${DATA_LABELS.fullyDiluted}">${fdvDisplay}</td>`
      + `<td data-label="${DATA_LABELS.volume}">${volumeDisplay}</td>`
      + `${renderChangeCell(item.pct_change_24h, DATA_LABELS.change24h)}`
      + `${renderChangeCell(item.pct_change_7d, DATA_LABELS.change7d)}`
      + `${renderChangeCell(item.pct_change_30d, DATA_LABELS.change30d)}`;
    const coinCell = tr.querySelector('td');
    if (coinCell) {
      const wrapper = document.createElement('div');
      wrapper.className = 'coin-cell';
      const logoUrl = typeof item.logo_url === 'string' ? item.logo_url.trim() : '';
      if (logoUrl) {
        const img = document.createElement('img');
        img.className = 'coin-logo';
        img.src = logoUrl;
        img.alt = displayName !== '—' ? displayName : coinId || 'Crypto';
        img.loading = 'lazy';
        img.width = 24;
        img.height = 24;
        wrapper.appendChild(img);
      }
      const nameSpan = document.createElement('span');
      nameSpan.className = 'coin-name';
      nameSpan.textContent = displayName !== '—' ? displayName : coinId || '—';
      wrapper.appendChild(nameSpan);
      coinCell.appendChild(wrapper);
    }
    const actionCell = document.createElement('td');
    actionCell.setAttribute('data-label', DATA_LABELS.details);
    if (coinId) {
      const link = document.createElement('a');
      link.className = 'details-link';
      link.textContent = 'Détails';
      link.href = `./coin.html?coin_id=${encodeURIComponent(coinId)}`;
      const labelName = displayName !== '—' ? displayName : coinId || 'cet actif';
      link.setAttribute('aria-label', `Voir les détails pour ${labelName}`);
      actionCell.appendChild(link);
    } else {
      actionCell.textContent = '—';
    }
    tr.appendChild(actionCell);
    fragment.appendChild(tr);
  });
  tbody.appendChild(fragment);
}

function getPaginationElements() {
  if (
    paginationElements?.container &&
    paginationElements.container.isConnected &&
    paginationElements.container.ownerDocument === document
  ) {
    return paginationElements;
  }
  const container =
    document.querySelector('[data-pagination]') || document.getElementById('market-pagination');
  if (!container) {
    paginationElements = null;
    return null;
  }
  paginationElements = {
    container,
    info: container.querySelector('[data-role="pagination-info"]'),
    pages: container.querySelector('[data-role="pagination-pages"]'),
    prev: container.querySelector('[data-role="pagination-prev"]'),
    next: container.querySelector('[data-role="pagination-next"]'),
  };
  return paginationElements;
}

function computePageCount(total, perPage) {
  const size = Math.max(1, Number(perPage) || DEFAULT_ROWS_PER_PAGE);
  return total > 0 ? Math.ceil(total / size) : 0;
}

function buildPaginationSequence(totalPages, currentPage) {
  if (totalPages <= 0) {
    return [];
  }
  if (totalPages <= 7) {
    return Array.from({ length: totalPages }, (_, index) => index + 1);
  }
  const pages = new Set([1, totalPages, currentPage]);
  pages.add(currentPage - 1);
  pages.add(currentPage + 1);
  if (currentPage <= 3) {
    for (let page = 2; page <= Math.min(5, totalPages - 1); page += 1) {
      pages.add(page);
    }
  } else if (currentPage >= totalPages - 2) {
    for (let page = Math.max(2, totalPages - 4); page < totalPages; page += 1) {
      pages.add(page);
    }
  }
  const sorted = Array.from(pages)
    .filter((page) => page >= 1 && page <= totalPages)
    .sort((a, b) => a - b);
  const sequence = [];
  let previous = null;
  sorted.forEach((page) => {
    if (previous !== null && page - previous > 1) {
      sequence.push('ellipsis');
    }
    sequence.push(page);
    previous = page;
  });
  return sequence;
}

function setCurrentPage(page) {
  const perPage = Math.max(1, Number(paginationState.perPage) || DEFAULT_ROWS_PER_PAGE);
  const totalPages = computePageCount(marketItems.length, perPage);
  const numeric = Number(page);
  const target = Number.isFinite(numeric) ? Math.floor(numeric) : 1;
  const clamped = totalPages > 0 ? Math.min(Math.max(target, 1), totalPages) : 1;
  if (clamped === paginationState.page) {
    return;
  }
  paginationState.page = clamped;
  renderSortedItems();
}

function updatePaginationControls(total, currentPage, perPage, totalPages) {
  const elements = getPaginationElements();
  if (!elements?.container) {
    return;
  }
  const { container, info, pages, prev, next } = elements;
  if (total <= 0) {
    container.hidden = true;
    if (info) {
      info.textContent = 'Aucun résultat';
    }
    if (pages) {
      pages.innerHTML = '';
    }
    if (prev) {
      prev.disabled = true;
      prev.onclick = null;
    }
    if (next) {
      next.disabled = true;
      next.onclick = null;
    }
    return;
  }

  container.hidden = false;
  const safePerPage = Math.max(1, Number(perPage) || DEFAULT_ROWS_PER_PAGE);
  const startIndex = (currentPage - 1) * safePerPage + 1;
  const endIndex = Math.min(total, startIndex + safePerPage - 1);
  if (info) {
    info.textContent = `Afficher les résultats de ${startIndex} à ${endIndex} sur ${total}`;
  }
  if (prev) {
    prev.disabled = currentPage <= 1;
    prev.onclick = currentPage > 1 ? () => setCurrentPage(currentPage - 1) : null;
  }
  if (next) {
    next.disabled = currentPage >= totalPages;
    next.onclick = currentPage < totalPages ? () => setCurrentPage(currentPage + 1) : null;
  }
  if (pages) {
    pages.innerHTML = '';
    const sequence = buildPaginationSequence(totalPages, currentPage);
    sequence.forEach((entry) => {
      if (entry === 'ellipsis') {
        const span = document.createElement('span');
        span.className = 'pagination-ellipsis';
        span.textContent = '…';
        pages.appendChild(span);
        return;
      }
      const pageNumber = Number(entry);
      const button = document.createElement('button');
      button.type = 'button';
      button.dataset.page = String(pageNumber);
      button.textContent = String(pageNumber);
      button.className = 'pagination-button';
      if (pageNumber === currentPage) {
        button.disabled = true;
        button.setAttribute('aria-current', 'page');
      }
      button.addEventListener('click', () => {
        setCurrentPage(pageNumber);
      });
      pages.appendChild(button);
    });
  }
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
  const sortedItems = [...marketItems];
  if (hasSort) {
    const accessor = SORTABLE_COLUMN_ACCESSORS.get(sortState.columnIndex);
    sortedItems.sort((a, b) =>
      compareNumericValues(accessor?.(a), accessor?.(b), sortState.direction),
    );
    applySortIndicators(sortState.columnIndex, sortState.direction);
  } else {
    clearSortIndicators();
  }
  const perPage = Math.max(1, Number(paginationState.perPage) || DEFAULT_ROWS_PER_PAGE);
  const total = sortedItems.length;
  const totalPages = computePageCount(total, perPage);
  let currentPage = paginationState.page;
  if (totalPages === 0) {
    currentPage = 1;
  } else if (currentPage > totalPages) {
    currentPage = totalPages;
  } else if (currentPage < 1) {
    currentPage = 1;
  }
  if (currentPage !== paginationState.page) {
    paginationState.page = currentPage;
  }
  const startIndex = total > 0 ? (currentPage - 1) * perPage : 0;
  const pageItems = total > 0 ? sortedItems.slice(startIndex, startIndex + perPage) : [];
  updatePaginationControls(total, currentPage, perPage, totalPages);
  renderRows(pageItems);
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
      paginationState.page = 1;
      if (marketItems.length) {
        renderSortedItems();
      }
    });
    boundSortableHeaders.add(th);
  });
}

export async function loadCryptos() {
  const statusEl = document.getElementById('status');
  if (statusEl) {
    statusEl.textContent = 'Chargement...';
  }
  const tableEl = document.getElementById('cryptos');
  if (tableEl) {
    tableEl.style.display = 'none';
  }
  const tbody = document.querySelector('#cryptos tbody');
  if (tbody) {
    tbody.innerHTML = '';
  }
  const pagination = getPaginationElements();
  if (pagination?.container) {
    pagination.container.hidden = true;
  }
  paginationState.page = 1;
  paginationState.perPage = DEFAULT_ROWS_PER_PAGE;
  initializeSorting();
  try {
    const rawItems = await fetchCoinGeckoMarkets({
      limit: COINGECKO_DEFAULT_LIMIT,
      perPage: COINGECKO_MAX_PER_PAGE,
    });
    marketItems = mapCoinGeckoItems(rawItems);
    updateSummary(marketItems);
    await renderMarketOverview(marketItems);
    renderSortedItems();
    if (tableEl) {
      tableEl.style.display = 'table';
    }
    if (statusEl) {
      statusEl.textContent = '';
    }
    const lastEl = document.getElementById('last-update');
    if (lastEl) {
      lastEl.textContent = `Dernière mise à jour : ${new Date().toISOString()} (source : CoinGecko API)`;
    }
    if (API_URL) {
      try {
        const diag = await fetch(`${API_URL}/diag`).then((r) => (r.ok ? r.json() : null));
        if (diag?.plan === 'demo') {
          const banner = document.getElementById('demo-banner');
          if (banner) {
            banner.style.display = 'block';
          }
        }
      } catch (error) {
        console.error(error);
      }
    }
  } catch (err) {
    marketItems = [];
    renderSortedItems();
    if (statusEl) {
      statusEl.innerHTML = `Erreur lors de la récupération des données <button id="retry">Réessayer</button>`;
      const retry = document.getElementById('retry');
      if (retry) {
        retry.onclick = loadCryptos;
      }
    }
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
  loadCryptos,
};

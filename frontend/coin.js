import { createAreaChart, refreshChartsTheme } from './charting.js';
import { initThemeToggle, onThemeChange } from './theme.js';
import { calculateAvailableRanges, pickInitialRange, syncRangeSelector } from './range.js';

const API_URL = document.querySelector('meta[name="api-url"]')?.content || '';
const PREFERRED_RANGE = '7d';
const RANGE_BUTTON_SELECTOR = '#range-selector [data-range]';
const MAX_RANGE_KEY = 'max';
const CHART_COLORS = {
  price: '--chart-price',
  marketCap: '--chart-market',
  volume: '--chart-volume',
};

const HISTORY_CHART_GROUP = 'coin-history-group';
const HISTORY_SERIES = [
  {
    key: 'price',
    elementId: 'price-chart',
    name: 'Prix ($)',
    dataKey: 'price',
    colorVar: CHART_COLORS.price,
    chartId: 'coin-history-price',
  },
  {
    key: 'market',
    elementId: 'market-cap-chart',
    name: 'Capitalisation ($)',
    dataKey: 'marketCap',
    colorVar: CHART_COLORS.marketCap,
    chartId: 'coin-history-market',
  },
  {
    key: 'volume',
    elementId: 'volume-chart',
    name: 'Volume 24h ($)',
    dataKey: 'volume',
    colorVar: CHART_COLORS.volume,
    chartId: 'coin-history-volume',
  },
];

const USD_SUFFIXES = [
  { threshold: 1_000_000_000_000, suffix: 'T$' },
  { threshold: 1_000_000_000, suffix: 'B$' },
  { threshold: 1_000_000, suffix: 'M$' },
  { threshold: 1_000, suffix: 'k$' },
];

const USD_COMPACT_FORMATTER = new Intl.NumberFormat('en-US', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
});

let currentCoinId = '';
let currentRange = null;
const historyCharts = new Map(
  HISTORY_SERIES.map(({ key, chartId }) => [key, { id: chartId, instance: null }]),
);
const historyCache = new Map();
let availableHistoryRanges = new Set();

function getHistoryChartEntry(key) {
  return historyCharts.get(key) || null;
}

function setHistoryChartInstance(key, chart) {
  const entry = historyCharts.get(key);
  if (!entry) {
    return;
  }
  entry.instance = chart || null;
}

function resetHistoryChartInstances() {
  historyCharts.forEach((entry) => {
    entry.instance = null;
  });
}

function getHistoryChartsSnapshot() {
  return HISTORY_SERIES.map(({ key }) => {
    const entry = historyCharts.get(key);
    return {
      key,
      id: entry?.id || '',
      instance: entry?.instance || null,
    };
  });
}

function resolveDataPointIndex(details) {
  if (!details || typeof details !== 'object') {
    return null;
  }
  const { dataPointIndex, selectedDataPoints } = details;
  if (Number.isInteger(dataPointIndex) && dataPointIndex >= 0) {
    return dataPointIndex;
  }
  if (Array.isArray(selectedDataPoints)) {
    for (const seriesPoints of selectedDataPoints) {
      if (!Array.isArray(seriesPoints) || seriesPoints.length === 0) {
        continue;
      }
      const lastIndex = seriesPoints[seriesPoints.length - 1];
      if (Number.isInteger(lastIndex) && lastIndex >= 0) {
        return lastIndex;
      }
    }
  }
  return null;
}

function syncHistoryTooltips(index) {
  if (!Number.isInteger(index) || index < 0) {
    return;
  }
  const exec = window?.ApexCharts?.exec;
  if (typeof exec !== 'function') {
    return;
  }
  getHistoryChartsSnapshot().forEach(({ id, instance }) => {
    if (!instance || !id) {
      return;
    }
    exec(id, 'tooltip.show', { seriesIndex: 0, dataPointIndex: index });
  });
}

function hideHistoryTooltips() {
  const exec = window?.ApexCharts?.exec;
  if (typeof exec !== 'function') {
    return;
  }
  getHistoryChartsSnapshot().forEach(({ id, instance }) => {
    if (!instance || !id) {
      return;
    }
    exec(id, 'tooltip.hide');
  });
}

function handleHistorySelection(_key, details) {
  const index = resolveDataPointIndex(details);
  if (index === null) {
    hideHistoryTooltips();
    return;
  }
  syncHistoryTooltips(index);
}

function buildHistoryEvents(key) {
  return {
    dataPointSelection(event, chartContext, config) {
      handleHistorySelection(key, config);
    },
    markerClick(event, chartContext, { dataPointIndex }) {
      handleHistorySelection(key, { dataPointIndex });
    },
  };
}

function getRangeContainer() {
  return document.getElementById('range-selector');
}

function setStatus(message) {
  const el = document.getElementById('status');
  if (!el) return;
  el.textContent = message;
}

function titleFromId(coinId) {
  if (!coinId) return 'Détails';
  return coinId
    .split(/[-_]/)
    .filter(Boolean)
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ');
}

function formatCurrency(value) {
  if (value === null || value === undefined) {
    return '—';
  }
  const digits = value >= 1 ? 2 : value >= 0.01 ? 4 : 6;
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

function formatUsd(value) {
  if (value === null || value === undefined) {
    return '—';
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric) || !Number.isFinite(numeric)) {
    return '—';
  }
  const abs = Math.abs(numeric);
  for (const { threshold, suffix } of USD_SUFFIXES) {
    if (abs >= threshold) {
      const scaled = numeric / threshold;
      const formatted = USD_COMPACT_FORMATTER.format(scaled);
      return `${formatted} ${suffix}`;
    }
  }
  return `${numeric.toLocaleString('en-US')} $`;
}

function formatDateTime(iso) {
  if (!iso) return 'inconnue';
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return date.toLocaleString('fr-FR', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

function normalizePointValue(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric) || !Number.isFinite(numeric)) {
    return null;
  }
  return numeric;
}

export function buildHistoricalDataset(points = []) {
  if (!Array.isArray(points) || points.length === 0) {
    return { categories: [], price: [], marketCap: [], volume: [] };
  }
  const categories = [];
  const price = [];
  const marketCap = [];
  const volume = [];
  points.forEach((point) => {
    const timestamp = point?.snapshot_at || '';
    categories.push(timestamp);
    price.push(normalizePointValue(point?.price));
    marketCap.push(normalizePointValue(point?.market_cap));
    volume.push(normalizePointValue(point?.volume_24h));
  });
  return { categories, price, marketCap, volume };
}

function extractTimestamps(points = []) {
  return (points || [])
    .map((point) => (typeof point?.snapshot_at === 'string' ? point.snapshot_at : null))
    .filter((value) => typeof value === 'string');
}

function updateRangeAvailability(points = []) {
  availableHistoryRanges = calculateAvailableRanges(extractTimestamps(points));
  const container = getRangeContainer();
  if (container) {
    syncRangeSelector(container, availableHistoryRanges);
  }
  return availableHistoryRanges;
}

function pruneUnavailableRange(range) {
  if (!availableHistoryRanges.has(range)) {
    return;
  }
  availableHistoryRanges = new Set(
    Array.from(availableHistoryRanges.values()).filter((key) => key !== range),
  );
  const container = getRangeContainer();
  if (container) {
    syncRangeSelector(container, availableHistoryRanges);
  }
}

function renderCategories(names) {
  const container = document.getElementById('categories');
  if (!container) return;
  container.innerHTML = '';
  if (!names || names.length === 0) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'Aucune catégorie renseignée.';
    container.appendChild(empty);
    return;
  }
  const wrap = document.createElement('div');
  wrap.className = 'badge-grid';
  names.forEach((name) => {
    const badge = document.createElement('span');
    badge.className = 'badge';
    badge.textContent = name;
    wrap.appendChild(badge);
  });
  container.appendChild(wrap);
}

function renderDetail(detail) {
  const rawName = typeof detail?.name === 'string' ? detail.name.trim() : '';
  const title = rawName || titleFromId(detail.coin_id || currentCoinId);
  const titleEl = document.getElementById('coin-title');
  const titleTextEl = document.getElementById('coin-title-text');
  if (titleTextEl) {
    titleTextEl.textContent = title;
  } else if (titleEl) {
    titleEl.textContent = title;
  }
  document.title = `Tokenlysis – ${title}`;
  const logoEl = document.getElementById('coin-logo');
  if (logoEl) {
    const rawLogo = typeof detail?.logo_url === 'string' ? detail.logo_url.trim() : '';
    if (rawLogo) {
      logoEl.setAttribute('src', rawLogo);
      logoEl.alt = title;
      logoEl.hidden = false;
      logoEl.removeAttribute('hidden');
    } else {
      logoEl.setAttribute('src', '');
      logoEl.alt = '';
      logoEl.hidden = true;
    }
  }
  const priceEl = document.getElementById('price-value');
  if (priceEl) {
    priceEl.textContent = formatCurrency(detail.price);
  }
  const priceUpdatedEl = document.getElementById('price-updated');
  if (priceUpdatedEl) {
    priceUpdatedEl.textContent = `Dernière mise à jour : ${formatDateTime(detail.snapshot_at)}`;
  }
  const marketCapEl = document.getElementById('market-cap-value');
  if (marketCapEl) {
    marketCapEl.textContent = formatUsd(detail.market_cap);
  }
  const volumeEl = document.getElementById('volume-value');
  if (volumeEl) {
    volumeEl.textContent = formatUsd(detail.volume_24h);
  }
  renderCategories(detail.category_names || []);
}

function setActiveRange(range) {
  document.querySelectorAll(RANGE_BUTTON_SELECTOR).forEach((button) => {
    const isActive = button.dataset.range === range;
    button.classList.toggle('active', isActive);
    button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
}

function showEmptyHistory(isEmpty) {
  const emptyEl = document.getElementById('history-empty');
  if (!emptyEl) return;
  emptyEl.hidden = !isEmpty;
}

function hasValues(series) {
  return Array.isArray(series) && series.some((value) => value !== null);
}

async function renderOrUpdateChart({
  key,
  elementId,
  name,
  data,
  categories,
  colorVar,
  chartId,
  chartGroup,
  events,
}) {
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  const entry = getHistoryChartEntry(key);
  const existing = entry?.instance || null;
  if (!existing) {
    const chart = await createAreaChart(element, {
      name,
      categories,
      data,
      colorVar,
      chartId,
      chartGroup,
      events,
    });
    setHistoryChartInstance(key, chart);
    return;
  }
  await existing.updateOptions(
    {
      xaxis: { categories },
    },
    false,
    true,
  );
  await existing.updateSeries(
    [
      {
        name,
        data,
      },
    ],
    true,
  );
}

async function renderHistory(points) {
  const dataset = buildHistoricalDataset(points);
  const hasHistory =
    dataset.categories.length > 0 &&
    HISTORY_SERIES.some(({ dataKey }) => hasValues(dataset[dataKey]));
  showEmptyHistory(!hasHistory);
  hideHistoryTooltips();
  await Promise.all(
    HISTORY_SERIES.map((definition) => {
      const entry = getHistoryChartEntry(definition.key);
      return renderOrUpdateChart({
        key: definition.key,
        elementId: definition.elementId,
        name: definition.name,
        data: dataset[definition.dataKey],
        categories: dataset.categories,
        colorVar: definition.colorVar,
        chartId: entry?.id,
        chartGroup: HISTORY_CHART_GROUP,
        events: buildHistoryEvents(definition.key),
      });
    }),
  );
}

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

async function getHistoryPoints(range) {
  const key = typeof range === 'string' && range.trim() ? range : MAX_RANGE_KEY;
  if (historyCache.has(key)) {
    return historyCache.get(key);
  }
  const data = await fetchJson(
    `${API_URL}/price/${encodeURIComponent(currentCoinId)}/history?range=${encodeURIComponent(key)}&vs=usd`,
  );
  const points = Array.isArray(data.points) ? data.points : [];
  historyCache.set(key, points);
  return points;
}

async function loadHistory(range, { force = false, pointsOverride } = {}) {
  if (!currentCoinId) {
    return;
  }
  if (!force && range === currentRange) {
    return;
  }
  let points = pointsOverride;
  if (!points) {
    points = await getHistoryPoints(range);
  } else {
    historyCache.set(range, points);
  }
  const hasPoints = Array.isArray(points) && points.length > 0;
  if (!hasPoints && range !== MAX_RANGE_KEY) {
    pruneUnavailableRange(range);
    const fallback = pickInitialRange(availableHistoryRanges, PREFERRED_RANGE);
    if (fallback && fallback !== range) {
      await loadHistory(fallback, { force: true });
      return;
    }
  }
  currentRange = range;
  setActiveRange(range);
  await renderHistory(points || []);
}

function bindRangeButtons() {
  document.querySelectorAll(RANGE_BUTTON_SELECTOR).forEach((button) => {
    button.addEventListener('click', async () => {
      const { range } = button.dataset;
      if (!range || button.disabled || !availableHistoryRanges.has(range)) return;
      setStatus("Chargement de l'historique...");
      try {
        await loadHistory(range);
        setStatus('');
      } catch (err) {
        console.error(err);
        setStatus("Impossible de récupérer l'historique des prix.");
      }
    });
  });
}

async function loadCoin() {
  if (!currentCoinId) {
    return;
  }
  setStatus('Chargement...');
  historyCache.clear();
  hideHistoryTooltips();
  availableHistoryRanges = new Set();
  currentRange = null;
  setActiveRange('');
  const container = getRangeContainer();
  if (container) {
    syncRangeSelector(container, new Set());
  }
  try {
    const detail = await fetchJson(`${API_URL}/price/${encodeURIComponent(currentCoinId)}`);
    renderDetail(detail);
    const maxPoints = await getHistoryPoints(MAX_RANGE_KEY);
    const ranges = updateRangeAvailability(maxPoints);
    if (!ranges.size) {
      showEmptyHistory(true);
      setStatus('Aucune donnée historique disponible pour cet actif.');
      return;
    }
    const initialRange = pickInitialRange(ranges, PREFERRED_RANGE) || MAX_RANGE_KEY;
    await loadHistory(initialRange, {
      force: true,
      pointsOverride: initialRange === MAX_RANGE_KEY ? maxPoints : undefined,
    });
    setStatus('');
  } catch (err) {
    console.error(err);
    setStatus('Erreur lors du chargement des données. Veuillez réessayer plus tard.');
  }
}

export async function init() {
  initThemeToggle('[data-theme-toggle]');
  onThemeChange((theme) => {
    refreshChartsTheme(theme);
  });
  const url = new URL(window.location.href);
  const coinId = url.searchParams.get('coin_id');
  if (!coinId) {
    setStatus('Aucune crypto sélectionnée. Retournez au tableau pour choisir un actif.');
    return;
  }
  currentCoinId = coinId;
  bindRangeButtons();
  await loadCoin();
}

if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', init);
}

export const __test__ = {
  buildHistoricalDataset,
  normalizePointValue,
  formatUsd,
  renderDetail,
  historySync: {
    registerInstance: (key, chart) => setHistoryChartInstance(key, chart),
    handleSelection: (key, details) => handleHistorySelection(key, details),
    syncTooltips: (index) => syncHistoryTooltips(index),
    clearTooltips: () => hideHistoryTooltips(),
    reset: () => resetHistoryChartInstances(),
  },
};

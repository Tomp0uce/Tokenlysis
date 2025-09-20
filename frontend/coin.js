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

let currentCoinId = '';
let currentRange = null;
let priceChart = null;
let marketChart = null;
let volumeChart = null;
const historyCache = new Map();
let availableHistoryRanges = new Set();

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
  return `${Number(value).toLocaleString('en-US')} USD`;
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
  const title = titleFromId(detail.coin_id || currentCoinId);
  const titleEl = document.getElementById('coin-title');
  if (titleEl) {
    titleEl.textContent = title;
  }
  document.title = `Tokenlysis – ${title}`;
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

async function renderOrUpdateChart({ key, elementId, name, data, categories, colorVar }) {
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  const existing =
    key === 'price' ? priceChart : key === 'market' ? marketChart : volumeChart;
  if (!existing) {
    const chart = await createAreaChart(element, { name, categories, data, colorVar });
    if (key === 'price') {
      priceChart = chart;
    } else if (key === 'market') {
      marketChart = chart;
    } else {
      volumeChart = chart;
    }
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
    (hasValues(dataset.price) || hasValues(dataset.marketCap) || hasValues(dataset.volume));
  showEmptyHistory(!hasHistory);
  await Promise.all([
    renderOrUpdateChart({
      key: 'price',
      elementId: 'price-chart',
      name: 'Prix (USD)',
      data: dataset.price,
      categories: dataset.categories,
      colorVar: CHART_COLORS.price,
    }),
    renderOrUpdateChart({
      key: 'market',
      elementId: 'market-cap-chart',
      name: 'Capitalisation (USD)',
      data: dataset.marketCap,
      categories: dataset.categories,
      colorVar: CHART_COLORS.marketCap,
    }),
    renderOrUpdateChart({
      key: 'volume',
      elementId: 'volume-chart',
      name: 'Volume 24h (USD)',
      data: dataset.volume,
      categories: dataset.categories,
      colorVar: CHART_COLORS.volume,
    }),
  ]);
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
};

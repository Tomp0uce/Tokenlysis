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

const SVG_NS = 'http://www.w3.org/2000/svg';

const SOCIAL_DEFINITIONS = [
  { key: 'website', label: 'Site officiel' },
  { key: 'twitter', label: 'Twitter' },
  { key: 'reddit', label: 'Reddit' },
  { key: 'github', label: 'GitHub' },
  { key: 'discord', label: 'Discord' },
  { key: 'telegram', label: 'Telegram' },
];

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

function createSvgElement(tag) {
  return document.createElementNS(SVG_NS, tag);
}

function appendPath(svg, d, { fill = 'currentColor', stroke, strokeWidth = '1.5', strokeLinecap = 'round', strokeLinejoin = 'round' } = {}) {
  const path = createSvgElement('path');
  path.setAttribute('d', d);
  if (fill === null) {
    path.setAttribute('fill', 'none');
  } else if (fill) {
    path.setAttribute('fill', fill);
  }
  if (stroke) {
    path.setAttribute('stroke', stroke);
    path.setAttribute('stroke-width', strokeWidth);
    path.setAttribute('stroke-linecap', strokeLinecap);
    path.setAttribute('stroke-linejoin', strokeLinejoin);
  }
  svg.appendChild(path);
}

const SOCIAL_ICON_RENDERERS = {
  website(svg) {
    const outer = createSvgElement('circle');
    outer.setAttribute('cx', '12');
    outer.setAttribute('cy', '12');
    outer.setAttribute('r', '9');
    outer.setAttribute('fill', 'none');
    outer.setAttribute('stroke', 'currentColor');
    outer.setAttribute('stroke-width', '1.5');
    svg.appendChild(outer);

    const horizontal = createSvgElement('path');
    horizontal.setAttribute('d', 'M3 12h18');
    horizontal.setAttribute('stroke', 'currentColor');
    horizontal.setAttribute('stroke-width', '1.5');
    horizontal.setAttribute('stroke-linecap', 'round');
    horizontal.setAttribute('fill', 'none');
    svg.appendChild(horizontal);

    appendPath(svg, 'M12 3c-3 4-3 14 0 18', {
      fill: null,
      stroke: 'currentColor',
      strokeWidth: '1.5',
    });
    appendPath(svg, 'M12 3c3 4 3 14 0 18', {
      fill: null,
      stroke: 'currentColor',
      strokeWidth: '1.5',
    });
    appendPath(svg, 'M4.5 9c3.2-2.2 11.8-2.2 15 0', {
      fill: null,
      stroke: 'currentColor',
      strokeWidth: '1.5',
    });
    appendPath(svg, 'M4.5 15c3.2 2.2 11.8 2.2 15 0', {
      fill: null,
      stroke: 'currentColor',
      strokeWidth: '1.5',
    });
  },
  twitter(svg) {
    appendPath(svg, 'M22.46 6c-.77.35-1.6.58-2.46.69a4.3 4.3 0 0 0 1.88-2.37 8.59 8.59 0 0 1-2.72 1.04 4.28 4.28 0 0 0-7.3 3.9 12.14 12.14 0 0 1-8.82-4.47 4.28 4.28 0 0 0 1.32 5.72 4.24 4.24 0 0 1-1.94-.54v.05a4.28 4.28 0 0 0 3.44 4.19 4.3 4.3 0 0 1-1.93.07 4.29 4.29 0 0 0 4 2.97A8.6 8.6 0 0 1 2 19.54a12.13 12.13 0 0 0 6.56 1.92c7.88 0 12.2-6.53 12.2-12.2 0-.19 0-.38-.01-.57A8.7 8.7 0 0 0 24 5.12a8.59 8.59 0 0 1-2.54.7Z');
  },
  reddit(svg) {
    appendPath(svg, 'M21 10.6c-.3 0-.6.1-.9.2-.7-1.4-2.1-2.3-3.6-2.3-1.1 0-2.1.4-2.9 1-.5-.5-1.2-.8-1.9-.8-1.7 0-3.1 1.3-3.1 2.9 0 .2 0 .4.1.6-2.4.1-4.3 1.9-4.3 4.1 0 2.3 2 4.1 4.5 4.1h8.8c2.5 0 4.5-1.9 4.5-4.1 0-1.5-.9-2.8-2.2-3.5a1.6 1.6 0 0 0 0-.2c0-.9-.7-1.5-1.5-1.5Zm-11.1 1c.5 0 .9.4.9.8s-.4.8-.9.8-.9-.4-.9-.8.4-.8.9-.8Zm6.6 4.9c-1.2.8-2.7 1-3.9 1s-2.7-.2-3.9-1c-.2-.1-.3-.4-.2-.6.1-.2.4-.3.6-.1.9.6 2.1.8 3.4.8s2.5-.3 3.4-.8c.2-.1.5-.1.6.1.1.2 0 .5-.2.6Zm-.4-3.3c-.5 0-.9-.4-.9-.8s.4-.8.9-.8.9.4.9.8-.4.8-.9.8Z');
  },
  github(svg) {
    appendPath(svg, 'M12 2c-3.3 0-6 2.8-6 6.2 0 2.7 1.6 4.9 3.8 5.7-.3.3-.5.8-.5 1.4v2.2c0 .2-.2.5-.5.5-2.3-.7-3.8-2.5-3.8-5.1 0-2.8 1.9-5 4.5-5.5.3-.1.5-.4.5-.7 0-.3-.2-.6-.5-.7-1-.3-2.1-.8-3.1-1.8-.2-.2-.5-.2-.7 0-.2.2-.2.5 0 .7.9.9 1.8 1.5 2.7 1.8-.6 1.3-.6 2.8.2 4.1.3.5.2 1.1-.3 1.4-.5.3-1.1.2-1.4-.3-.7-1.1-.8-2.5-.2-3.8-1.6.6-2.8 2.1-2.8 3.9 0 1.6.8 3.1 2 4-.4.5-1 .9-1.6 1.1-.3.1-.5.4-.4.7 0 .3.3.5.6.5 2.7 0 4.8 1.2 5.8 2.9.2.4.7.5 1.1.3.2-.1.3-.3.3-.5v-3.6c0-.4-.1-.7-.3-1 3.1-.8 5.4-3.6 5.4-7C18 4.8 15.3 2 12 2Z');
  },
  discord(svg) {
    appendPath(svg, 'M21 6.5c-1.6-.7-3.2-1-4.9-1.1-.2.3-.4.7-.6 1-1.8-.3-3.6-.3-5.4 0-.2-.4-.4-.7-.6-1-1.7.1-3.3.4-4.9 1.1-1.3 1.9-2 4.1-2 6.3 0 .1 0 .2 0 .3 2.1 1.5 4.1 2.5 6.1 3 .3-.4.6-.9.8-1.4-.9-.3-1.7-.7-2.4-1.3.2-.1.3-.2.5-.3 2.3 1 4.8 1 7.1 0 .2.1.4.2.5.3-.7.6-1.5 1-2.4 1.3.3.5.6 1 .9 1.4 2-.5 4-1.5 6.1-3 0-.1 0-.2 0-.3 0-2.2-.7-4.4-2-6.3Zm-10 6.2c-.7 0-1.3-.6-1.3-1.3 0-.7.6-1.3 1.3-1.3.7 0 1.3.6 1.3 1.3 0 .7-.6 1.3-1.3 1.3Zm5 0c-.7 0-1.3-.6-1.3-1.3 0-.7.6-1.3 1.3-1.3.7 0 1.3.6 1.3 1.3 0 .7-.6 1.3-1.3 1.3Z');
  },
  telegram(svg) {
    appendPath(svg, 'M21.5 3.5 2.4 11.2c-.9.4-.9 1.5-.1 1.9l4.6 1.8 1.7 5.5c.3.9 1.5 1.1 2 .3l2.3-3.4 4.8 3.7c.8.6 2 .2 2.2-.8l3-14.3c.2-.9-.7-1.6-1.4-1.2Z');
  },
};

function createSocialIcon(key) {
  const svg = createSvgElement('svg');
  svg.setAttribute('viewBox', '0 0 24 24');
  svg.setAttribute('aria-hidden', 'true');
  const renderer = SOCIAL_ICON_RENDERERS[key];
  if (renderer) {
    renderer(svg);
  }
  return svg;
}

function sanitizeSocialUrl(value) {
  if (typeof value !== 'string') {
    return '';
  }
  const trimmed = value.trim();
  if (!trimmed) {
    return '';
  }
  try {
    const url = new URL(trimmed);
    if (url.protocol !== 'http:' && url.protocol !== 'https:') {
      return '';
    }
    return trimmed;
  } catch (err) {
    return '';
  }
}

function renderSocialLinks(links) {
  const container = document.getElementById('social-links');
  if (!container) {
    return;
  }
  container.innerHTML = '';
  container.classList.add('social-links');
  const normalized = [];
  const seen = new Set();
  const source = (links && typeof links === 'object') ? links : {};
  SOCIAL_DEFINITIONS.forEach(({ key, label }) => {
    const sanitized = sanitizeSocialUrl(source[key]);
    if (sanitized && !seen.has(sanitized)) {
      seen.add(sanitized);
      normalized.push({ key, label, url: sanitized });
    }
  });
  if (!normalized.length) {
    const empty = document.createElement('p');
    empty.className = 'empty-state';
    empty.textContent = 'Aucun lien officiel disponible.';
    container.appendChild(empty);
    return;
  }
  normalized.forEach(({ key, label, url }) => {
    const anchor = document.createElement('a');
    anchor.className = 'social-link';
    anchor.href = url;
    anchor.target = '_blank';
    anchor.rel = 'noopener noreferrer';
    anchor.setAttribute('aria-label', `Ouvrir ${label}`);
    const icon = createSocialIcon(key);
    const text = document.createElement('span');
    text.textContent = label;
    anchor.append(icon, text);
    container.appendChild(anchor);
  });
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
  renderSocialLinks(detail?.social_links || {});
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

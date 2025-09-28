import {
  createRadialGauge,
  updateRadialGauge,
  createAreaChart,
  refreshChartsTheme,
} from './charting.js';
import { initThemeToggle, onThemeChange } from './theme.js';
import { syncRangeSelector } from './range.js';
import {
  computeSentimentSnapshots,
  collectSnapshotElements,
  renderSentimentSnapshots,
} from './sentiment.js';

const API_URL = document.querySelector('meta[name="api-url"]')?.content || '';
const API_BASE = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL;
const DEFAULT_RANGE = '3m';
const DEFAULT_CLASSIFICATION = 'Indéterminé';
const RANGE_TO_DAYS = {
  '1m': 30,
  '3m': 90,
  '6m': 180,
  '1y': 365,
};

let gaugeChart = null;
let historyChart = null;
let activeRange = DEFAULT_RANGE;
let rangeInitialized = false;
let latestDatapoint = null;
let historyDatapoints = [];
let snapshotElements = null;
let latestAvailable = true;
let historyAvailable = true;

function getFetch(fetchImpl) {
  if (typeof fetchImpl === 'function') {
    return fetchImpl;
  }
  if (typeof fetch === 'function') {
    return fetch;
  }
  return null;
}

function normalizeTimestamp(value) {
  if (value instanceof Date) {
    return value.toISOString().replace('.000Z', 'Z');
  }
  if (typeof value !== 'string') {
    try {
      return new Date(value).toISOString().replace('.000Z', 'Z');
    } catch (error) {
      console.error('normalizeTimestamp failed', error);
      return new Date().toISOString().replace('.000Z', 'Z');
    }
  }
  const trimmed = value.trim();
  if (trimmed.endsWith('+00:00')) {
    return `${trimmed.slice(0, -6)}Z`;
  }
  if (trimmed.endsWith('Z')) {
    return trimmed;
  }
  const parsed = Date.parse(trimmed);
  if (!Number.isNaN(parsed)) {
    return new Date(parsed).toISOString().replace('.000Z', 'Z');
  }
  return trimmed || new Date().toISOString().replace('.000Z', 'Z');
}

function setErrorBanner(message) {
  const banner = document.getElementById('fear-greed-error');
  if (!banner) {
    return;
  }
  if (!message) {
    banner.textContent = '';
    banner.hidden = true;
  } else {
    banner.textContent = message;
    banner.hidden = false;
  }
}

function hideVisuals() {
  const gaugeContainer = document.getElementById('fear-greed-gauge');
  const historyContainer = document.getElementById('fear-greed-history');
  if (gaugeContainer) {
    gaugeContainer.hidden = true;
  }
  if (historyContainer) {
    historyContainer.hidden = true;
  }
}

function showVisuals() {
  const gaugeContainer = document.getElementById('fear-greed-gauge');
  const historyContainer = document.getElementById('fear-greed-history');
  if (gaugeContainer) {
    gaugeContainer.hidden = false;
  }
  if (historyContainer) {
    historyContainer.hidden = false;
  }
}

function refreshAvailability() {
  if (latestAvailable && historyAvailable) {
    showVisuals();
    setErrorBanner(null);
  }
}

function formatHttpStatus(status) {
  if (typeof status === 'number' && Number.isFinite(status)) {
    return status;
  }
  return 'réseau';
}

function rangeToDays(range) {
  if (typeof range !== 'string') {
    return null;
  }
  const key = range.trim().toLowerCase();
  if (!key || key === 'max') {
    return null;
  }
  if (Object.prototype.hasOwnProperty.call(RANGE_TO_DAYS, key)) {
    return RANGE_TO_DAYS[key];
  }
  if (key === 'ytd') {
    const now = new Date();
    const start = new Date(Date.UTC(now.getUTCFullYear(), 0, 1));
    const diff = Math.floor((now.getTime() - start.getTime()) / (24 * 60 * 60 * 1000)) + 1;
    return diff > 0 ? diff : null;
  }
  if (key.endsWith('d')) {
    const parsed = Number.parseInt(key.slice(0, -1), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed : null;
  }
  if (key.endsWith('y')) {
    const parsed = Number.parseInt(key.slice(0, -1), 10);
    return Number.isFinite(parsed) && parsed > 0 ? parsed * 365 : null;
  }
  return null;
}

function sentimentElements() {
  return {
    valueEl: document.getElementById('fear-greed-value'),
    gaugeContainer: document.getElementById('fear-greed-gauge'),
  };
}

function formatSentiment(value) {
  const numeric = Number(value);
  if (!Number.isFinite(numeric)) {
    return '0';
  }
  return String(Math.round(numeric));
}

function setActiveRange(range) {
  const container = document.getElementById('fear-greed-range');
  if (!container) {
    return;
  }
  container.querySelectorAll('[data-range]').forEach((button) => {
    const isActive = button.dataset.range === range;
    button.classList.toggle('active', isActive);
    button.setAttribute('aria-pressed', isActive ? 'true' : 'false');
  });
  activeRange = range;
}

function updateSnapshotSummary() {
  if (!snapshotElements) {
    snapshotElements = collectSnapshotElements();
  }
  if (!snapshotElements || snapshotElements.size === 0) {
    return;
  }
  const snapshots = computeSentimentSnapshots(latestDatapoint, historyDatapoints);
  renderSentimentSnapshots(snapshotElements, snapshots);
}

async function loadLatest(fetchImpl) {
  const { valueEl, gaugeContainer } = sentimentElements();
  if (!valueEl || !gaugeContainer) {
    return null;
  }
  const fetcher = getFetch(fetchImpl);
  if (!fetcher) {
    return null;
  }
  try {
    const response = await fetcher(`${API_BASE}/fng/latest`);
    if (!response?.ok) {
      const error = new Error(`HTTP ${response?.status ?? 'error'}`);
      error.status = response?.status;
      throw error;
    }
    const payload = await response.json();
    const rawScore = Number(payload?.score ?? payload?.value ?? 0);
    const value = Number.isFinite(rawScore) ? Math.round(rawScore) : 0;
    const classification = String(payload?.label || payload?.classification || '').trim() || DEFAULT_CLASSIFICATION;
    const timestamp = normalizeTimestamp(
      typeof payload?.timestamp === 'string' ? payload.timestamp : new Date(),
    );

    valueEl.textContent = formatSentiment(value);

    latestDatapoint = { timestamp, value, classification };
    updateSnapshotSummary();

    if (!gaugeChart) {
      gaugeChart = await createRadialGauge(gaugeContainer, { value, classification });
    } else {
      await updateRadialGauge(gaugeChart, { value, classification });
    }
    latestAvailable = true;
    refreshAvailability();
    return gaugeChart;
  } catch (error) {
    console.error(error);
    valueEl.textContent = '0';
    latestDatapoint = null;
    updateSnapshotSummary();
    if (gaugeChart) {
      await updateRadialGauge(gaugeChart, { value: 0, classification: 'Indisponible' });
    }
    latestAvailable = false;
    const statusText = formatHttpStatus(error?.status);
    setErrorBanner(`Fear & Greed indisponible (HTTP ${statusText})`);
    hideVisuals();
    return null;
  }
}

async function loadHistory(range = activeRange, fetchImpl) {
  const container = document.getElementById('fear-greed-history');
  const errorEl = document.getElementById('history-error');
  if (!container || !errorEl) {
    return null;
  }
  const fetcher = getFetch(fetchImpl);
  if (!fetcher) {
    return null;
  }
  try {
    const days = rangeToDays(range);
    const query = typeof days === 'number' && days > 0 ? `?days=${encodeURIComponent(days)}` : '';
    const response = await fetcher(`${API_BASE}/fng/history${query}`);
    if (!response?.ok) {
      const error = new Error(`HTTP ${response?.status ?? 'error'}`);
      error.status = response?.status;
      throw error;
    }
    const payload = await response.json();
    const rawPoints = Array.isArray(payload?.points) ? payload.points : [];
    const points = rawPoints
      .map((point) => {
        const rawTimestamp = point?.timestamp ?? point?.time ?? null;
        const timestamp = rawTimestamp !== null && rawTimestamp !== undefined
          ? normalizeTimestamp(
              typeof rawTimestamp === 'number' ? new Date(rawTimestamp) : rawTimestamp,
            )
          : null;
        if (!timestamp) {
          return null;
        }
        const score = Number(point?.score ?? point?.value ?? 0);
        const numeric = Number.isFinite(score) ? Math.round(score) : 0;
        const label = String(point?.label || point?.classification || '').trim() || DEFAULT_CLASSIFICATION;
        return { timestamp, value: numeric, classification: label };
      })
      .filter(Boolean)
      .sort((a, b) => Date.parse(a.timestamp) - Date.parse(b.timestamp));
    if (!points.length) {
      errorEl.hidden = false;
      errorEl.textContent = 'Historique indisponible pour la période sélectionnée.';
      historyDatapoints = [];
      updateSnapshotSummary();
      if (historyChart) {
        await historyChart.updateSeries(
          [
            {
              name: 'Indice Fear & Greed',
              data: [],
            },
          ],
          true,
        );
      }
      historyAvailable = true;
      refreshAvailability();
      return null;
    }
    errorEl.hidden = true;
    historyDatapoints = points;
    updateSnapshotSummary();
    const categories = points
      .map((point) => point?.timestamp)
      .filter((ts) => typeof ts === 'string');
    const data = points.map((point) => {
      const numeric = Number(point?.value ?? 0);
      return Number.isFinite(numeric) ? numeric : 0;
    });

    if (!historyChart) {
      historyChart = await createAreaChart(container, {
        name: 'Indice Fear & Greed',
        categories,
        data,
        colorVar: '--chart-sentiment',
        xAxisType: 'datetime',
        yFormatter: formatSentiment,
        tooltipFormatter: formatSentiment,
        banding: 'fear-greed',
      });
    } else {
      await historyChart.updateOptions(
        {
          xaxis: { categories, type: 'datetime' },
        },
        false,
        true,
      );
      await historyChart.updateSeries(
        [
          {
            name: 'Indice Fear & Greed',
            data,
          },
        ],
        true,
      );
    }
    const effectiveRange = typeof payload?.range === 'string' ? payload.range : range;
    setActiveRange(effectiveRange);
    historyAvailable = true;
    refreshAvailability();
    return historyChart;
  } catch (error) {
    console.error(error);
    errorEl.hidden = false;
    errorEl.textContent = 'Historique indisponible pour la période sélectionnée.';
    historyDatapoints = [];
    updateSnapshotSummary();
    historyAvailable = false;
    const statusText = formatHttpStatus(error?.status);
    setErrorBanner(`Fear & Greed indisponible (HTTP ${statusText})`);
    hideVisuals();
    return null;
  }
}

function bindRangeButtons() {
  const container = document.getElementById('fear-greed-range');
  if (!container || rangeInitialized) {
    return;
  }
  rangeInitialized = true;
  container.querySelectorAll('[data-range]').forEach((button) => {
    button.addEventListener('click', async () => {
      const { range } = button.dataset;
      if (!range || range === activeRange || button.disabled) {
        return;
      }
      try {
        await loadHistory(range);
      } catch (error) {
        console.error(error);
      }
    });
  });
}

export async function init() {
  latestAvailable = true;
  historyAvailable = true;
  setErrorBanner(null);
  showVisuals();
  initThemeToggle('[data-theme-toggle]');
  onThemeChange((theme) => refreshChartsTheme(theme));
  setActiveRange(DEFAULT_RANGE);
  snapshotElements = collectSnapshotElements();
  updateSnapshotSummary();
  const rangeContainer = document.getElementById('fear-greed-range');
  if (rangeContainer) {
    syncRangeSelector(rangeContainer, new Set(['1m', '3m', '6m', '1y', 'ytd', 'max']));
  }
  await loadLatest();
  await loadHistory(DEFAULT_RANGE);
  bindRangeButtons();
}

if (typeof window !== 'undefined') {
  window.addEventListener('DOMContentLoaded', init);
}

export const __test__ = {
  loadLatest,
  loadHistory,
  setActiveRange,
};

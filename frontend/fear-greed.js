import {
  createRadialGauge,
  updateRadialGauge,
  createAreaChart,
  refreshChartsTheme,
} from './charting.js';
import { initThemeToggle, onThemeChange } from './theme.js';
import { syncRangeSelector } from './range.js';

const API_URL = document.querySelector('meta[name="api-url"]')?.content || '';
const API_BASE = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL;
const DEFAULT_RANGE = '90d';
const DEFAULT_CLASSIFICATION = 'Indéterminé';

let gaugeChart = null;
let historyChart = null;
let activeRange = DEFAULT_RANGE;
let rangeInitialized = false;

function getFetch(fetchImpl) {
  if (typeof fetchImpl === 'function') {
    return fetchImpl;
  }
  if (typeof fetch === 'function') {
    return fetch;
  }
  return null;
}

function sentimentElements() {
  return {
    valueEl: document.getElementById('fear-greed-value'),
    classificationEl: document.getElementById('fear-greed-classification'),
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

async function loadLatest(fetchImpl) {
  const { valueEl, classificationEl, gaugeContainer } = sentimentElements();
  if (!valueEl || !classificationEl || !gaugeContainer) {
    return null;
  }
  const fetcher = getFetch(fetchImpl);
  if (!fetcher) {
    return null;
  }
  try {
    const response = await fetcher(`${API_BASE}/fear-greed/latest`);
    if (!response?.ok) {
      throw new Error(`HTTP ${response?.status ?? 'error'}`);
    }
    const payload = await response.json();
    const rawValue = Number(payload?.value ?? 0);
    const value = Number.isFinite(rawValue) ? Math.round(rawValue) : 0;
    const classification = String(payload?.classification || '').trim() || DEFAULT_CLASSIFICATION;

    valueEl.textContent = formatSentiment(value);
    classificationEl.textContent = classification;

    if (!gaugeChart) {
      gaugeChart = await createRadialGauge(gaugeContainer, { value, classification });
    } else {
      await updateRadialGauge(gaugeChart, { value, classification });
    }
    return gaugeChart;
  } catch (error) {
    console.error(error);
    valueEl.textContent = '0';
    classificationEl.textContent = 'Indisponible';
    if (gaugeChart) {
      await updateRadialGauge(gaugeChart, { value: 0, classification: 'Indisponible' });
    }
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
    const response = await fetcher(`${API_BASE}/fear-greed/history?range=${encodeURIComponent(range)}`);
    if (!response?.ok) {
      throw new Error(`HTTP ${response?.status ?? 'error'}`);
    }
    const payload = await response.json();
    const points = Array.isArray(payload?.points) ? payload.points : [];
    if (!points.length) {
      errorEl.hidden = false;
      errorEl.textContent = 'Historique indisponible pour la période sélectionnée.';
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
      return null;
    }
    errorEl.hidden = true;
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
    return historyChart;
  } catch (error) {
    console.error(error);
    errorEl.hidden = false;
    errorEl.textContent = 'Historique indisponible pour la période sélectionnée.';
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
  initThemeToggle('[data-theme-toggle]');
  onThemeChange((theme) => refreshChartsTheme(theme));
  setActiveRange(DEFAULT_RANGE);
  const rangeContainer = document.getElementById('fear-greed-range');
  if (rangeContainer) {
    syncRangeSelector(rangeContainer, new Set(['30d', '90d', '1y', 'max']));
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

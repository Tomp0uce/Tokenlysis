const API_URL = document.querySelector('meta[name="api-url"]')?.content || '';
const DEFAULT_RANGE = '7d';
const RANGE_BUTTON_SELECTOR = '#range-selector [data-range]';
const CHART_DIMENSIONS = { width: 600, height: 260, padding: 24 };
const AXIS_TICK_LENGTH = 6;
const MAX_Y_TICKS = 5;
const MAX_X_TICKS = 5;

function createSvgElement(tag, attributes = {}) {
  const element = document.createElementNS('http://www.w3.org/2000/svg', tag);
  Object.entries(attributes).forEach(([key, value]) => {
    element.setAttribute(key, String(value));
  });
  return element;
}

function formatAxisDateLabel(iso) {
  if (!iso) {
    return '';
  }
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) {
    return iso;
  }
  return new Intl.DateTimeFormat('en-US', {
    day: '2-digit',
    month: 'short',
  }).format(date);
}

function formatAxisValueLabel(value) {
  if (value === null || value === undefined) {
    return '';
  }
  const numeric = Number(value);
  if (Number.isNaN(numeric) || !Number.isFinite(numeric)) {
    return '';
  }
  const fractionDigits = numeric >= 1 ? 2 : 4;
  return new Intl.NumberFormat('en-US', {
    maximumFractionDigits: fractionDigits,
  }).format(numeric);
}

function generateLinearTicks(min, max, count) {
  if (!Number.isFinite(min) || !Number.isFinite(max) || count <= 0) {
    return [];
  }
  if (Math.abs(max - min) < Number.EPSILON) {
    return Array.from({ length: count }, () => min);
  }
  if (count === 1) {
    return [min];
  }
  const step = (max - min) / (count - 1);
  return Array.from({ length: count }, (_, index) => min + index * step);
}

function generateIndexTicks(length, count) {
  if (length <= 0 || count <= 0) {
    return [];
  }
  if (count >= length) {
    return Array.from({ length }, (_, index) => index);
  }
  const maxIndex = length - 1;
  const step = maxIndex / (count - 1);
  const indices = new Set();
  for (let i = 0; i < count; i += 1) {
    const rawIndex = Math.round(i * step);
    const clamped = Math.min(maxIndex, Math.max(0, rawIndex));
    indices.add(clamped);
  }
  indices.add(0);
  indices.add(maxIndex);
  return Array.from(indices).sort((a, b) => a - b);
}

let currentCoinId = '';
let currentRange = null;

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

async function fetchJson(url) {
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}

function renderCategories(names) {
  const container = document.getElementById('categories');
  if (!container) return;
  container.innerHTML = '';
  if (!names || names.length === 0) {
    container.textContent = 'Aucune catégorie renseignée.';
    return;
  }
  const title = document.createElement('h2');
  title.textContent = 'Catégories';
  container.appendChild(title);
  const wrap = document.createElement('div');
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

function clearSvg(svg) {
  while (svg.firstChild) {
    svg.removeChild(svg.firstChild);
  }
}

function renderChart(svg, series, color) {
  clearSvg(svg);
  if (!series.length) {
    svg.setAttribute('data-empty', 'true');
    return;
  }
  svg.removeAttribute('data-empty');
  const { width, height, padding } = CHART_DIMENSIONS;
  svg.setAttribute('viewBox', `0 0 ${width} ${height}`);
  const usableWidth = width - padding * 2;
  const usableHeight = height - padding * 2;
  const min = Math.min(...series.map((point) => point.value));
  const max = Math.max(...series.map((point) => point.value));
  const span = max - min || 1;
  const step = series.length > 1 ? usableWidth / (series.length - 1) : 0;
  const coordinates = series.map((point, index) => {
    const x = padding + (series.length > 1 ? index * step : usableWidth / 2);
    const y = padding + usableHeight - ((point.value - min) / span) * usableHeight;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const leftX = padding;
  const rightX = width - padding;
  const topY = padding;
  const bottomY = height - padding;
  const yTickValues = generateLinearTicks(
    min,
    max,
    Math.min(MAX_Y_TICKS, Math.max(2, series.length))
  );
  const xTickIndexes = generateIndexTicks(
    series.length,
    Math.min(MAX_X_TICKS, Math.max(2, series.length))
  );
  const toX = (index) =>
    padding + (series.length > 1 ? index * step : usableWidth / 2);
  const toY = (value) =>
    padding + usableHeight - ((value - min) / span) * usableHeight;

  const axisY = createSvgElement('g', { class: 'axis axis-y' });
  axisY.appendChild(
    createSvgElement('line', {
      x1: leftX,
      y1: topY,
      x2: leftX,
      y2: bottomY,
    })
  );
  yTickValues.forEach((value, index) => {
    const tickY = index === 0 ? bottomY : index === yTickValues.length - 1 ? topY : toY(value);
    axisY.appendChild(
      createSvgElement('line', {
        x1: leftX - AXIS_TICK_LENGTH,
        y1: tickY,
        x2: leftX,
        y2: tickY,
      })
    );
    const textAttributes = {
      x: leftX - AXIS_TICK_LENGTH - 2,
      y:
        index === 0
          ? bottomY - 4
          : index === yTickValues.length - 1
          ? topY + 4
          : tickY,
      'text-anchor': 'end',
      'dominant-baseline':
        index === 0 ? 'alphabetic' : index === yTickValues.length - 1 ? 'hanging' : 'middle',
    };
    const text = createSvgElement('text', textAttributes);
    const role =
      index === 0
        ? 'axis-y-min'
        : index === yTickValues.length - 1
        ? 'axis-y-max'
        : 'axis-y-tick';
    text.setAttribute('data-role', role);
    text.setAttribute('data-value', String(value));
    text.textContent = formatAxisValueLabel(value);
    axisY.appendChild(text);
  });

  const axisX = createSvgElement('g', { class: 'axis axis-x' });
  axisX.appendChild(
    createSvgElement('line', {
      x1: leftX,
      y1: bottomY,
      x2: rightX,
      y2: bottomY,
    })
  );
  xTickIndexes.forEach((tickIndex, position) => {
    const point = series[tickIndex];
    const x = toX(tickIndex);
    axisX.appendChild(
      createSvgElement('line', {
        x1: x,
        y1: bottomY,
        x2: x,
        y2: bottomY + AXIS_TICK_LENGTH,
      })
    );
    const value = point?.snapshot_at || '';
    const formattedValue = formatAxisDateLabel(value);
    const isFirst = position === 0;
    const isLast = position === xTickIndexes.length - 1;
    const text = createSvgElement('text', {
      x,
      y: bottomY + AXIS_TICK_LENGTH + 8,
      'text-anchor': isFirst ? 'start' : isLast ? 'end' : 'middle',
      'dominant-baseline': 'hanging',
    });
    const role = isFirst ? 'axis-x-min' : isLast ? 'axis-x-max' : 'axis-x-tick';
    text.setAttribute('data-role', role);
    text.setAttribute('data-value', value);
    text.textContent = formattedValue;
    axisX.appendChild(text);
    if (isFirst && isLast) {
      const maxText = createSvgElement('text', {
        x,
        y: bottomY + AXIS_TICK_LENGTH + 8,
        'text-anchor': 'end',
        'dominant-baseline': 'hanging',
      });
      maxText.setAttribute('data-role', 'axis-x-max');
      maxText.setAttribute('data-value', value);
      maxText.textContent = formattedValue;
      axisX.appendChild(maxText);
    }
  });

  svg.appendChild(axisY);
  svg.appendChild(axisX);

  const polyline = createSvgElement('polyline', {
    fill: 'none',
    stroke: color,
    'stroke-width': 2,
    points: coordinates.join(' '),
  });
  svg.appendChild(polyline);
  series.forEach((point, index) => {
    const x = padding + (series.length > 1 ? index * step : usableWidth / 2);
    const y = padding + usableHeight - ((point.value - min) / span) * usableHeight;
    const circle = createSvgElement('circle', {
      cx: x.toFixed(2),
      cy: y.toFixed(2),
      r: 3,
      fill: color,
    });
    const title = createSvgElement('title');
    title.textContent = `${formatDateTime(point.snapshot_at)} • ${Number(point.value).toLocaleString('en-US')}`;
    circle.appendChild(title);
    svg.appendChild(circle);
  });
}

function buildSeries(points, key) {
  return points
    .map((point) => {
      const raw = point[key];
      if (raw === null || raw === undefined) {
        return null;
      }
      const numeric = Number(raw);
      if (Number.isNaN(numeric) || !Number.isFinite(numeric)) {
        return null;
      }
      return { snapshot_at: point.snapshot_at, value: numeric };
    })
    .filter(Boolean);
}

function renderHistory(points) {
  const priceSeries = buildSeries(points, 'price');
  const marketSeries = buildSeries(points, 'market_cap');
  const volumeSeries = buildSeries(points, 'volume_24h');
  const hasData = priceSeries.length || marketSeries.length || volumeSeries.length;
  showEmptyHistory(!hasData);
  const priceSvg = document.getElementById('price-chart');
  const marketSvg = document.getElementById('market-cap-chart');
  const volumeSvg = document.getElementById('volume-chart');
  if (priceSvg) {
    renderChart(priceSvg, priceSeries, '#1976d2');
  }
  if (marketSvg) {
    renderChart(marketSvg, marketSeries, '#388e3c');
  }
  if (volumeSvg) {
    renderChart(volumeSvg, volumeSeries, '#f57c00');
  }
}

async function loadHistory(range, { force = false } = {}) {
  if (!currentCoinId) {
    return;
  }
  if (!force && range === currentRange) {
    return;
  }
  const data = await fetchJson(
    `${API_URL}/price/${encodeURIComponent(currentCoinId)}/history?range=${encodeURIComponent(range)}&vs=usd`
  );
  currentRange = range;
  setActiveRange(range);
  renderHistory(data.points || []);
}

function bindRangeButtons() {
  document.querySelectorAll(RANGE_BUTTON_SELECTOR).forEach((button) => {
    button.addEventListener('click', async () => {
      const { range } = button.dataset;
      if (!range) return;
      setStatus('Chargement de l\'historique...');
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
  try {
    const detail = await fetchJson(`${API_URL}/price/${encodeURIComponent(currentCoinId)}`);
    renderDetail(detail);
    await loadHistory(DEFAULT_RANGE, { force: true });
    setStatus('');
  } catch (err) {
    console.error(err);
    setStatus('Erreur lors du chargement des données. Veuillez réessayer plus tard.');
  }
}

export async function init() {
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
  buildSeries,
  renderChart,
};

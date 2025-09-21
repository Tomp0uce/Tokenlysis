const hasDocument = typeof document !== 'undefined';
const API_URL = hasDocument
  ? document.querySelector('meta[name="api-url"]')?.content || ''
  : '';
const API_BASE = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL;
const STATUS_CLASSES = ['status-ok', 'status-warn', 'status-error', 'status-unknown'];

function toFiniteNumber(value) {
  if (value === null || value === undefined) {
    return null;
  }
  const num = Number(value);
  if (Number.isNaN(num) || !Number.isFinite(num)) {
    return null;
  }
  return num;
}

function computeRatio(numerator, denominator) {
  const num = toFiniteNumber(numerator);
  const den = toFiniteNumber(denominator);
  if (den === null || den <= 0) {
    return null;
  }
  if (num === null) {
    return null;
  }
  const safeNum = Math.max(num, 0);
  const ratio = safeNum / den;
  if (!Number.isFinite(ratio)) {
    return null;
  }
  return ratio;
}

function classifyEtlRatio(ratio) {
  if (ratio === null) {
    return 'unknown';
  }
  if (ratio >= 0.95 && ratio <= 1.05) {
    return 'ok';
  }
  if ((ratio >= 0.8 && ratio < 0.95) || (ratio > 1.05 && ratio <= 1.2)) {
    return 'warn';
  }
  return 'error';
}

function classifyBudgetRatio(ratio) {
  if (ratio === null) {
    return 'unknown';
  }
  if (ratio <= 0.75) {
    return 'ok';
  }
  if (ratio <= 0.9) {
    return 'warn';
  }
  return 'error';
}

export function evaluateRatios(diag) {
  const etlRatio = computeRatio(diag?.last_etl_items, diag?.top_n);
  const budgetRatio = computeRatio(diag?.monthly_call_count, diag?.quota);
  return {
    etl: {
      ratio: etlRatio,
      status: classifyEtlRatio(etlRatio),
    },
    budget: {
      ratio: budgetRatio,
      status: classifyBudgetRatio(budgetRatio),
    },
  };
}

function formatNumber(value) {
  const num = toFiniteNumber(value);
  if (num === null) {
    return '—';
  }
  try {
    return new Intl.NumberFormat('fr-FR').format(Math.round(num));
  } catch (err) {
    console.error('formatNumber failed', err);
    return String(Math.round(num));
  }
}

function formatRatio(ratio) {
  if (ratio === null) {
    return '—';
  }
  const percentage = ratio * 100;
  if (!Number.isFinite(percentage)) {
    return '—';
  }
  const formatted = percentage.toFixed(1).replace('.', ',');
  return `${formatted} %`;
}

function applyStatusClass(element, status) {
  if (!element) {
    return;
  }
  element.classList.remove(...STATUS_CLASSES);
  element.classList.add(`status-${status}`);
}

function updateRatioElement(elementId, metric) {
  if (!hasDocument) {
    return;
  }
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  applyStatusClass(element, metric.status);
  element.textContent = formatRatio(metric.ratio);
}

function updateNumberElement(elementId, value) {
  if (!hasDocument) {
    return;
  }
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  element.textContent = formatNumber(value);
}

function updateTextElement(elementId, value) {
  if (!hasDocument) {
    return;
  }
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  const text = typeof value === 'string' && value.trim() ? value.trim() : '—';
  element.textContent = text;
}

function setStatusMessage(message, status) {
  if (!hasDocument) {
    return;
  }
  const element = document.getElementById('diag-status');
  if (!element) {
    return;
  }
  element.textContent = message;
  element.classList.remove('status-ok', 'status-warn', 'status-error');
  if (status) {
    element.classList.add(`status-${status}`);
  }
}

function renderDiag(diag) {
  const metrics = evaluateRatios(diag);
  updateNumberElement('etl-count', diag?.last_etl_items);
  updateNumberElement('etl-target', diag?.top_n);
  updateRatioElement('etl-ratio', metrics.etl);

  updateNumberElement('budget-count', diag?.monthly_call_count);
  updateNumberElement('budget-quota', diag?.quota);
  updateRatioElement('budget-ratio', metrics.budget);

  updateTextElement('diag-source', diag?.data_source);
  updateTextElement('diag-plan', diag?.plan);
  updateTextElement('diag-base-url', diag?.base_url);
  updateTextElement('diag-granularity', diag?.granularity);
  updateTextElement('diag-last-refresh', diag?.last_refresh_at);
}

async function fetchDiag() {
  const prefix = API_BASE || '';
  const response = await fetch(`${prefix}/diag`, {
    headers: { 'Accept': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

export async function loadDiagnostics() {
  if (!hasDocument) {
    return;
  }
  try {
    setStatusMessage('Chargement des diagnostics…', 'warn');
    const diag = await fetchDiag();
    renderDiag(diag);
    setStatusMessage('Diagnostics chargés', 'ok');
  } catch (error) {
    console.error('loadDiagnostics failed', error);
    setStatusMessage('Erreur lors du chargement des diagnostics', 'error');
  }
}

if (hasDocument) {
  const init = () => {
    loadDiagnostics();
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
}

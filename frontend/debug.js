const hasDocument = typeof document !== 'undefined';
const API_URL = hasDocument
  ? document.querySelector('meta[name="api-url"]')?.content || ''
  : '';
const API_BASE = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL;
const STATUS_CLASSES = ['status-ok', 'status-warn', 'status-error', 'status-unknown'];
const STATUS_PRIORITY = { unknown: 0, ok: 1, warn: 2, error: 3 };
const CATEGORY_REASON_LABELS = {
  missing_categories: 'Catégories manquantes',
  stale_timestamp: 'Horodatage obsolète',
};

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

function mergeStatus(current, candidate) {
  const currentPriority = STATUS_PRIORITY[current] ?? 0;
  const candidatePriority = STATUS_PRIORITY[candidate] ?? 0;
  if (candidatePriority > currentPriority) {
    return candidate;
  }
  return current || 'unknown';
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

export function summarizeCategoryIssues(items) {
  const entries = Array.isArray(items) ? items : [];
  let missing = 0;
  let stale = 0;
  let both = 0;
  for (const entry of entries) {
    const reasons = Array.isArray(entry?.reasons) ? entry.reasons : [];
    const hasMissing = reasons.includes('missing_categories');
    const hasStale = reasons.includes('stale_timestamp');
    if (hasMissing) {
      missing += 1;
    }
    if (hasStale) {
      stale += 1;
    }
    if (hasMissing && hasStale) {
      both += 1;
    }
  }
  return {
    total: entries.length,
    missing,
    stale,
    both,
  };
}

function parseGranularityHours(granularity) {
  const numericValue = toFiniteNumber(granularity);
  if (numericValue !== null && numericValue > 0) {
    return numericValue;
  }
  if (typeof granularity === 'string') {
    const trimmed = granularity.trim().toLowerCase();
    if (!trimmed) {
      return 12;
    }
    if (trimmed.endsWith('h')) {
      const candidate = trimmed.slice(0, -1).trim().replace(',', '.');
      const hours = toFiniteNumber(candidate);
      if (hours !== null && hours > 0) {
        return hours;
      }
    }
    const fallback = trimmed.replace(',', '.');
    const parsed = toFiniteNumber(fallback);
    if (parsed !== null && parsed > 0) {
      return parsed;
    }
  }
  return 12;
}

function computeDifferenceHours(lastRefreshAt, nowMs = Date.now()) {
  if (!lastRefreshAt) {
    return null;
  }
  const parsed = Date.parse(lastRefreshAt);
  if (Number.isNaN(parsed)) {
    return null;
  }
  const nowValue = toFiniteNumber(nowMs);
  const reference = nowValue !== null ? nowValue : Date.now();
  const deltaMs = reference - parsed;
  if (!Number.isFinite(deltaMs)) {
    return null;
  }
  const deltaHours = deltaMs / (60 * 60 * 1000);
  if (!Number.isFinite(deltaHours)) {
    return null;
  }
  if (deltaHours < 0) {
    return 0;
  }
  return deltaHours;
}

export function evaluateFreshness({ lastRefreshAt, granularity, stale, nowMs = Date.now() }) {
  const differenceHours = computeDifferenceHours(lastRefreshAt, nowMs);
  const granularityHours = parseGranularityHours(granularity);
  let ratio = null;
  if (differenceHours !== null && granularityHours > 0) {
    ratio = differenceHours / granularityHours;
    if (!Number.isFinite(ratio)) {
      ratio = null;
    }
  }

  let status = 'unknown';
  if (stale === true) {
    status = 'error';
  } else if (ratio !== null) {
    if (ratio <= 1) {
      status = 'ok';
    } else if (ratio <= 2) {
      status = 'warn';
    } else {
      status = 'error';
    }
  } else if (differenceHours !== null) {
    status = 'warn';
  }

  const staleFlag = stale === true ? true : stale === false ? false : null;

  return {
    differenceHours,
    granularityHours,
    ratio,
    status,
    stale: staleFlag,
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

function formatHours(value) {
  const hours = toFiniteNumber(value);
  if (hours === null) {
    return '—';
  }
  const safeValue = Math.max(hours, 0);
  try {
    const formatter = new Intl.NumberFormat('fr-FR', {
      minimumFractionDigits: 1,
      maximumFractionDigits: 1,
    });
    return `${formatter.format(safeValue)} h`;
  } catch (err) {
    console.error('formatHours failed', err);
    return `${safeValue.toFixed(1).replace('.', ',')} h`;
  }
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

function updateStaleElement(elementId, stale) {
  if (!hasDocument) {
    return;
  }
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  let status = 'unknown';
  let text = '—';
  if (stale === true) {
    status = 'error';
    text = 'Obsolète';
  } else if (stale === false) {
    status = 'ok';
    text = 'À jour';
  }
  applyStatusClass(element, status);
  element.textContent = text;
}

function updateFreshnessElement(elementId, metrics) {
  if (!hasDocument) {
    return;
  }
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  const parts = [];
  const differenceText = formatHours(metrics?.differenceHours);
  if (differenceText !== '—') {
    parts.push(differenceText);
  }
  const granularityText = formatHours(metrics?.granularityHours);
  if (granularityText !== '—') {
    parts.push(`granularité ${granularityText}`);
  }
  const text = parts.length > 0 ? parts.join(' / ') : '—';
  const status = metrics?.status || 'unknown';
  applyStatusClass(element, status);
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

function renderMarketMeta(market, diag, nowMs = Date.now()) {
  const lastRefresh = market?.last_refresh_at ?? diag?.last_refresh_at ?? null;
  updateTextElement('market-source', market?.data_source ?? diag?.data_source);
  updateTextElement('market-last-refresh', lastRefresh);
  updateStaleElement('market-stale', market?.stale);
  const freshness = evaluateFreshness({
    lastRefreshAt: lastRefresh,
    granularity: diag?.granularity,
    stale: market?.stale,
    nowMs,
  });
  updateFreshnessElement('market-lag', freshness);
  return freshness;
}

function updateCategoryIssuesList(items) {
  if (!hasDocument) {
    return;
  }
  const list = document.getElementById('category-issues-list');
  if (!list) {
    return;
  }
  list.innerHTML = '';
  if (!Array.isArray(items) || items.length === 0) {
    const li = document.createElement('li');
    li.textContent = 'Aucun écart détecté';
    list.appendChild(li);
    return;
  }
  for (const item of items) {
    const li = document.createElement('li');
    const coinId = item?.coin_id ?? 'inconnu';
    const names = Array.isArray(item?.category_names) ? item.category_names : [];
    const reasons = Array.isArray(item?.reasons) ? item.reasons : [];
    const labels = reasons.map((reason) => CATEGORY_REASON_LABELS[reason] || reason);
    const updatedAt = typeof item?.updated_at === 'string' && item.updated_at.trim()
      ? item.updated_at
      : 'inconnue';
    const categoriesText = names.length > 0 ? `catégories : ${names.join(', ')}` : 'aucune catégorie';
    const reasonsText = labels.length > 0 ? labels.join(', ') : 'raisons inconnues';
    li.textContent = `${coinId} — ${reasonsText} — ${categoriesText} — mise à jour : ${updatedAt}`;
    list.appendChild(li);
  }
}

function renderCategoryDiagnostics(payload) {
  const items = Array.isArray(payload?.items) ? payload.items : [];
  const summary = summarizeCategoryIssues(items);
  updateTextElement('category-generated-at', payload?.generated_at);
  const thresholdHours = toFiniteNumber(payload?.stale_after_hours);
  const thresholdText = thresholdHours === null ? '—' : formatHours(thresholdHours);
  updateTextElement('category-threshold', thresholdText);
  updateNumberElement('category-issue-count', summary.total);
  updateNumberElement('category-missing-count', summary.missing);
  updateNumberElement('category-stale-count', summary.stale);
  updateNumberElement('category-both-count', summary.both);
  updateCategoryIssuesList(items);
  return summary;
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

async function fetchMarketMeta() {
  const prefix = API_BASE || '';
  const response = await fetch(`${prefix}/markets/top?limit=1`, {
    headers: { 'Accept': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function fetchCategoryDiagnostics() {
  const prefix = API_BASE || '';
  const response = await fetch(`${prefix}/debug/categories`, {
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
    let market = null;
    let marketError = null;
    try {
      market = await fetchMarketMeta();
    } catch (error) {
      marketError = error;
      console.error('fetchMarketMeta failed', error);
    }
    const freshness = renderMarketMeta(market, diag, Date.now());
    let categoryPayload = null;
    let categoryError = null;
    try {
      categoryPayload = await fetchCategoryDiagnostics();
    } catch (error) {
      categoryError = error;
      console.error('fetchCategoryDiagnostics failed', error);
    }
    const categorySummary = renderCategoryDiagnostics(categoryPayload);

    let status = 'ok';
    const notes = [];
    if (marketError) {
      status = mergeStatus(status, 'warn');
      notes.push('métadonnées marchés indisponibles');
    } else if (freshness.status === 'error') {
      status = mergeStatus(status, 'error');
      notes.push('rafraîchissement en retard');
    } else if (freshness.status === 'warn') {
      status = mergeStatus(status, 'warn');
      notes.push('rafraîchissement à surveiller');
    } else if (freshness.status === 'unknown') {
      status = mergeStatus(status, 'warn');
      notes.push('rafraîchissement indéterminé');
    }

    if (categoryError) {
      status = mergeStatus(status, 'warn');
      notes.push('diagnostic catégories indisponible');
    } else if (categorySummary.total > 0) {
      status = mergeStatus(status, 'warn');
      notes.push('catégories à mettre à jour');
    }

    const message = notes.length > 0
      ? `Diagnostics chargés (${notes.join(' ; ')})`
      : 'Diagnostics chargés';
    setStatusMessage(message, status);
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

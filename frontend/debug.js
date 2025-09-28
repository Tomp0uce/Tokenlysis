import { applyTheme, getInitialTheme, initThemeToggle } from './theme.js';

function hasDocument() {
  return typeof document !== 'undefined';
}

const API_URL = hasDocument()
  ? document.querySelector('meta[name="api-url"]')?.content || ''
  : '';
const API_BASE = API_URL.endsWith('/') ? API_URL.slice(0, -1) : API_URL;
const STATUS_CLASSES = ['status-ok', 'status-warn', 'status-error', 'status-unknown'];
const STATUS_PRIORITY = { unknown: 0, ok: 1, warn: 2, error: 3 };
const CATEGORY_REASON_LABELS = {
  missing_categories: 'Catégories manquantes',
  stale_timestamp: 'Horodatage obsolète',
};

let lastDiagnostics = null;

function cloneDiagnostics(value) {
  if (!value || typeof value !== 'object') {
    return null;
  }
  if (typeof structuredClone === 'function') {
    try {
      return structuredClone(value);
    } catch (error) {
      console.warn('structuredClone failed, falling back to JSON clone', error);
    }
  }
  try {
    return JSON.parse(JSON.stringify(value));
  } catch (error) {
    console.warn('JSON clone failed, returning shallow copy', error);
    return { ...value };
  }
}

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

export function normalizeBudgetCategories(diag) {
  const totalCalls = toFiniteNumber(diag?.monthly_call_count);
  const safeTotal = totalCalls !== null && totalCalls > 0 ? totalCalls : null;
  const raw = diag?.monthly_call_categories;
  const entries = [];

  if (raw && typeof raw === 'object') {
    for (const [rawName, rawCount] of Object.entries(raw)) {
      const count = toFiniteNumber(rawCount);
      if (count === null || count <= 0) {
        continue;
      }
      const name = typeof rawName === 'string' && rawName.trim()
        ? rawName.trim()
        : 'uncategorized';
      entries.push({ name, count });
    }
  }

  entries.sort((a, b) => {
    if (b.count !== a.count) {
      return b.count - a.count;
    }
    return a.name.localeCompare(b.name);
  });

  const fallbackTotal = entries.reduce((sum, item) => sum + item.count, 0);
  const denominator = safeTotal !== null && safeTotal > 0 ? safeTotal : fallbackTotal;
  const categories = entries.map((item) => {
    const ratio = denominator > 0 ? item.count / denominator : null;
    return {
      name: item.name,
      count: item.count,
      ratio: Number.isFinite(ratio) ? ratio : null,
    };
  });

  return {
    total: safeTotal !== null ? safeTotal : fallbackTotal,
    categories,
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

function formatCategoryName(name) {
  if (typeof name !== 'string') {
    return 'Autres';
  }
  const trimmed = name.trim();
  if (!trimmed || trimmed === 'uncategorized') {
    return 'Autres';
  }
  const normalised = trimmed.replace(/[_-]+/g, ' ').toLowerCase();
  return normalised.charAt(0).toUpperCase() + normalised.slice(1);
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

function formatTimestamp(value) {
  if (value instanceof Date) {
    const dateValue = value;
    if (!Number.isFinite(dateValue.getTime())) {
      return '—';
    }
    try {
      const formatter = new Intl.DateTimeFormat('fr-FR', {
        dateStyle: 'medium',
        timeStyle: 'medium',
        timeZone: 'UTC',
      });
      return `${formatter.format(dateValue)} UTC`;
    } catch (err) {
      console.error('formatTimestamp failed', err);
      return dateValue.toISOString();
    }
  }

  if (typeof value !== 'string') {
    return '—';
  }

  const trimmed = value.trim();
  if (!trimmed) {
    return '—';
  }

  const parsed = Date.parse(trimmed);
  if (Number.isNaN(parsed)) {
    return trimmed;
  }

  try {
    const formatter = new Intl.DateTimeFormat('fr-FR', {
      dateStyle: 'medium',
      timeStyle: 'medium',
      timeZone: 'UTC',
    });
    return `${formatter.format(new Date(parsed))} UTC`;
  } catch (err) {
    console.error('formatTimestamp failed', err);
    return trimmed;
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
  if (!hasDocument()) {
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
  if (!hasDocument()) {
    return;
  }
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  element.textContent = formatNumber(value);
}

function updateBudgetBreakdown(diag, targetId = 'budget-breakdown-list') {
  if (!hasDocument()) {
    return;
  }
  const list = document.getElementById(targetId);
  if (!list) {
    return;
  }
  list.innerHTML = '';
  const breakdown = normalizeBudgetCategories(diag);
  const categories = Array.isArray(breakdown?.categories) ? breakdown.categories : [];
  if (categories.length === 0) {
    const li = document.createElement('li');
    li.textContent = 'Aucune donnée catégorisée';
    list.appendChild(li);
    return;
  }
  for (const item of categories) {
    const li = document.createElement('li');
    const label = formatCategoryName(item?.name);
    const countText = formatNumber(item?.count);
    let ratioText = '';
    if (item?.ratio !== null && Number.isFinite(item.ratio)) {
      const formatted = formatRatio(item.ratio);
      if (formatted !== '—') {
        ratioText = ` — ${formatted}`;
      }
    }
    li.textContent = `${label} : ${countText}${ratioText}`;
    list.appendChild(li);
  }
}

function updateTextElement(elementId, value) {
  if (!hasDocument()) {
    return;
  }
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  const text = typeof value === 'string' && value.trim() ? value.trim() : '—';
  element.textContent = text;
}

function updateTimestampElement(elementId, value) {
  if (!hasDocument()) {
    return;
  }
  const element = document.getElementById(elementId);
  if (!element) {
    return;
  }
  element.textContent = formatTimestamp(value);
}

function updateStaleElement(elementId, stale) {
  if (!hasDocument()) {
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
  if (!hasDocument()) {
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
  if (!hasDocument()) {
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
  if (diag && typeof diag === 'object') {
    const snapshot = cloneDiagnostics(diag);
    if (snapshot) {
      lastDiagnostics = snapshot;
    }
  }
  const current = lastDiagnostics || (diag && typeof diag === 'object' ? diag : {});
  const etl = current?.etl ?? {};
  const cgUsage = current?.coingecko_usage ?? {};
  const cmcUsage = current?.coinmarketcap_usage ?? {};
  const fngCache = current?.fng_cache ?? {};
  const metrics = evaluateRatios(current);
  updateNumberElement('etl-count', etl?.last_etl_items ?? current?.last_etl_items);
  updateNumberElement('etl-target', etl?.top_n ?? current?.top_n);
  updateRatioElement('etl-ratio', metrics.etl);

  updateNumberElement('budget-count', cgUsage?.monthly_call_count ?? current?.monthly_call_count);
  updateNumberElement('budget-quota', cgUsage?.quota ?? current?.quota);
  updateRatioElement('budget-ratio', metrics.budget);
  updateBudgetBreakdown({
    monthly_call_count: cgUsage?.monthly_call_count ?? current?.monthly_call_count,
    monthly_call_categories:
      cgUsage?.monthly_call_categories ?? current?.monthly_call_categories,
  });

  updateNumberElement('cmc-budget-count', cmcUsage?.monthly_call_count);
  updateNumberElement('cmc-budget-quota', cmcUsage?.quota);
  const cmcRatioValue = computeRatio(
    cmcUsage?.monthly_call_count,
    cmcUsage?.quota,
  );
  updateRatioElement('cmc-budget-ratio', {
    ratio: cmcRatioValue,
    status: classifyBudgetRatio(cmcRatioValue),
  });
  updateBudgetBreakdown(
    {
      monthly_call_count: cmcUsage?.monthly_call_count,
      monthly_call_categories: cmcUsage?.monthly_call_categories,
    },
    'cmc-budget-breakdown-list',
  );

  updateTextElement('diag-source', etl?.data_source ?? current?.data_source);
  updateTextElement('diag-plan', cgUsage?.plan ?? current?.plan);
  const baseUrl = current?.base_url ?? current?.providers?.coingecko?.base_url;
  updateTextElement('diag-base-url', baseUrl);
  updateTextElement('diag-granularity', etl?.granularity ?? current?.granularity);
  updateTimestampElement('diag-last-refresh', etl?.last_refresh_at ?? current?.last_refresh_at);
  updateTimestampElement(
    'fear-greed-last-refresh',
    fngCache?.last_refresh ?? current?.fear_greed_last_refresh,
  );
  updateNumberElement('fear-greed-count', fngCache?.rows ?? current?.fear_greed_count);
}

function applyUsageOverrides(payload) {
  if (!payload || typeof payload !== 'object') {
    return;
  }
  const base = cloneDiagnostics(lastDiagnostics) || {};

  const coingecko = payload.coingecko;
  if (coingecko && typeof coingecko === 'object') {
    const usage = { ...(base.coingecko_usage ?? {}) };
    if (Object.prototype.hasOwnProperty.call(coingecko, 'plan')) {
      usage.plan = coingecko.plan;
    }
    if (Object.prototype.hasOwnProperty.call(coingecko, 'monthly_call_count')) {
      usage.monthly_call_count = coingecko.monthly_call_count;
      base.monthly_call_count = coingecko.monthly_call_count;
    }
    if (Object.prototype.hasOwnProperty.call(coingecko, 'quota')) {
      usage.quota = coingecko.quota;
      base.quota = coingecko.quota;
    }
    if (Object.prototype.hasOwnProperty.call(coingecko, 'remaining')) {
      usage.remaining = coingecko.remaining;
    }
    base.coingecko_usage = usage;
    if (typeof usage.plan === 'string') {
      base.plan = usage.plan;
    }
  }

  const coinmarketcap = payload.coinmarketcap;
  if (coinmarketcap && typeof coinmarketcap === 'object') {
    const usage = { ...(base.coinmarketcap_usage ?? {}) };
    if (Object.prototype.hasOwnProperty.call(coinmarketcap, 'plan')) {
      usage.plan = coinmarketcap.plan;
    }
    if (Object.prototype.hasOwnProperty.call(coinmarketcap, 'monthly_call_count')) {
      usage.monthly_call_count = coinmarketcap.monthly_call_count;
    }
    if (Object.prototype.hasOwnProperty.call(coinmarketcap, 'quota')) {
      usage.quota = coinmarketcap.quota;
    }
    if (Object.prototype.hasOwnProperty.call(coinmarketcap, 'remaining')) {
      usage.remaining = coinmarketcap.remaining;
    }
    if (Object.prototype.hasOwnProperty.call(coinmarketcap, 'monthly')) {
      usage.monthly = coinmarketcap.monthly;
    }
    base.coinmarketcap_usage = usage;
  }

  const updated = cloneDiagnostics(base) || base;
  lastDiagnostics = updated;
  renderDiag(updated);
}

function renderMarketMeta(market, diag, nowMs = Date.now()) {
  const lastRefresh = market?.last_refresh_at ?? diag?.last_refresh_at ?? null;
  updateTextElement('market-source', market?.data_source ?? diag?.data_source);
  updateTimestampElement('market-last-refresh', lastRefresh);
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
  if (!hasDocument()) {
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

function renderProviders(providers) {
  if (!hasDocument()) {
    return;
  }
  const container = document.getElementById('providers-list');
  if (!container) {
    return;
  }
  container.innerHTML = '';
  if (!providers || typeof providers !== 'object') {
    const paragraph = document.createElement('p');
    paragraph.textContent = 'Aucun fournisseur configuré';
    container.appendChild(paragraph);
    return;
  }

  const entries = Object.entries(providers);
  if (entries.length === 0) {
    const paragraph = document.createElement('p');
    paragraph.textContent = 'Aucun fournisseur configuré';
    container.appendChild(paragraph);
    return;
  }

  for (const [key, info] of entries) {
    const card = document.createElement('article');
    card.dataset.provider = key;
    card.classList.add('provider-card');

    const baseUrl = typeof info?.base_url === 'string' ? info.base_url : '';

    const title = document.createElement('h3');
    title.textContent = key.charAt(0).toUpperCase() + key.slice(1);
    card.appendChild(title);

    const basePara = document.createElement('p');
    basePara.innerHTML = `Base : <span data-role="base-url">${info?.base_url ?? '—'}</span>`;
    card.appendChild(basePara);

    const keyPara = document.createElement('p');
    keyPara.innerHTML = `Clé masquée : <span data-role="masked-key">${info?.api_key_masked ?? ''}</span>`;
    card.appendChild(keyPara);

    const endpointsList = document.createElement('ul');
    endpointsList.classList.add('provider-endpoints');

    for (const [endpointName, endpointInfo] of Object.entries(info || {})) {
      if (endpointName === 'base_url' || endpointName === 'api_key_masked') {
        continue;
      }
      let endpointData = null;
      if (endpointInfo && typeof endpointInfo === 'object') {
        endpointData = endpointInfo;
      } else if (typeof endpointInfo === 'string' && endpointInfo.trim()) {
        endpointData = { path: endpointInfo.trim() };
      } else {
        continue;
      }

      const item = document.createElement('li');
      const label = document.createElement('span');
      const rawPath = endpointData?.path ?? endpointData?.url ?? endpointName;
      const pathText =
        typeof rawPath === 'string' && rawPath.trim()
          ? rawPath.trim()
          : String(endpointName);
      label.textContent = pathText;
      item.appendChild(label);

      const docCandidate =
        endpointData?.doc_url ??
        endpointData?.docUrl ??
        endpointData?.documentation_url ??
        endpointData?.documentation;
      if (typeof docCandidate === 'string' && docCandidate.trim()) {
        const docLink = document.createElement('a');
        docLink.href = docCandidate;
        docLink.target = '_blank';
        docLink.rel = 'noreferrer';
        docLink.dataset.role = 'doc-link';
        docLink.textContent = 'Documentation';
        item.appendChild(document.createTextNode(' '));
        item.appendChild(docLink);
      }

      let safeCandidate =
        endpointData?.safe_url ?? endpointData?.safeUrl ?? endpointData?.url ?? null;
      if (typeof safeCandidate !== 'string' || !safeCandidate.trim()) {
        const rawPath =
          (typeof endpointData?.path === 'string' && endpointData.path.trim()) || '';
        if (rawPath.startsWith('http')) {
          safeCandidate = rawPath;
        } else {
          safeCandidate = null;
        }
      }

      if (typeof safeCandidate === 'string' && safeCandidate.trim()) {
        const safeLink = document.createElement('a');
        safeLink.href = safeCandidate;
        safeLink.target = '_blank';
        safeLink.rel = 'noreferrer';
        safeLink.dataset.role = 'safe-link';
        safeLink.textContent = safeCandidate;
        item.appendChild(document.createElement('br'));
        item.appendChild(safeLink);
      }

      endpointsList.appendChild(item);
    }

    if (endpointsList.childElementCount === 0) {
      const emptyItem = document.createElement('li');
      emptyItem.textContent = 'Aucun endpoint déclaré';
      endpointsList.appendChild(emptyItem);
    }

    card.appendChild(endpointsList);
    container.appendChild(card);
  }
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

async function fetchUsageSnapshot() {
  const prefix = API_BASE || '';
  const response = await fetch(`${prefix}/diag/refresh-usage`, {
    method: 'POST',
    headers: { 'Accept': 'application/json' },
  });
  if (!response.ok) {
    throw new Error(`HTTP ${response.status}`);
  }
  return response.json();
}

async function refreshUsage(button) {
  if (!hasDocument()) {
    return;
  }
  const control = button || document.querySelector('[data-role="refresh-usage"]');
  if (!control) {
    return;
  }
  control.disabled = true;
  setStatusMessage('Mise à jour des crédits…', 'warn');
  try {
    const payload = await fetchUsageSnapshot();
    applyUsageOverrides(payload);
    setStatusMessage('Crédits mis à jour depuis les API.', 'ok');
  } catch (error) {
    console.error('refreshUsage failed', error);
    setStatusMessage('Erreur lors de la mise à jour des crédits', 'error');
  } finally {
    control.disabled = false;
  }
}

function initUsageButton() {
  if (!hasDocument()) {
    return;
  }
  const button = document.querySelector('[data-role="refresh-usage"]');
  if (!button) {
    return;
  }
  if (button.dataset.usageBound === 'true') {
    return;
  }
  button.dataset.usageBound = 'true';
  button.addEventListener('click', () => {
    refreshUsage(button);
  });
}

export async function loadDiagnostics() {
  if (!hasDocument()) {
    return;
  }
  try {
    setStatusMessage('Chargement des diagnostics…', 'warn');
    const diag = await fetchDiag();
    renderDiag(diag);
    renderProviders(diag?.providers);
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

let themeInitialized = false;

function ensureThemeInitialized() {
  if (themeInitialized || !hasDocument()) {
    return;
  }
  const initialTheme = getInitialTheme();
  applyTheme(initialTheme);
  initThemeToggle('[data-theme-toggle]');
  themeInitialized = true;
}

export function initializeDebugPage() {
  if (!hasDocument()) {
    return Promise.resolve();
  }
  ensureThemeInitialized();
  initUsageButton();
  return loadDiagnostics();
}

if (hasDocument()) {
  const init = () => {
    initializeDebugPage();
  };
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init, { once: true });
  } else {
    init();
  }
}

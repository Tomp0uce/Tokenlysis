import { resolveFearGreedBand } from './charting.js';

export const SENTIMENT_PERIODS = [
  { key: 'today', lookbackDays: 0 },
  { key: 'yesterday', lookbackDays: 1 },
  { key: 'week', lookbackDays: 7 },
  { key: 'month', lookbackDays: 30 },
];

function normalizePoint(point) {
  if (!point) {
    return null;
  }
  const rawTimestamp = point.timestamp;
  const timestamp =
    typeof rawTimestamp === 'string' || rawTimestamp instanceof Date
      ? new Date(rawTimestamp)
      : null;
  if (!timestamp || Number.isNaN(timestamp.getTime())) {
    return null;
  }
  const numericValue = Number(point.value);
  if (!Number.isFinite(numericValue)) {
    return null;
  }
  const classification = typeof point.classification === 'string' ? point.classification.trim() : '';
  return {
    time: timestamp.getTime(),
    value: numericValue,
    classification,
  };
}

function targetTime(baseTime, lookbackDays) {
  const safeDays = Number.isFinite(lookbackDays) ? lookbackDays : 0;
  const date = new Date(baseTime);
  date.setUTCHours(23, 59, 59, 999);
  if (safeDays > 0) {
    date.setUTCDate(date.getUTCDate() - safeDays);
  }
  return date.getTime();
}

export function computeSentimentSnapshots(latest, historyPoints = [], { periods = SENTIMENT_PERIODS } = {}) {
  const normalizedHistory = Array.isArray(historyPoints)
    ? historyPoints.map(normalizePoint).filter(Boolean)
    : [];
  const normalizedLatest = normalizePoint(latest);
  const timeline = [...normalizedHistory];
  if (normalizedLatest) {
    timeline.push(normalizedLatest);
  }
  timeline.sort((a, b) => a.time - b.time);
  const reference = normalizedLatest ?? timeline.at(-1) ?? null;
  const baseTime = reference ? reference.time : null;
  const result = new Map();
  const effectivePeriods = Array.isArray(periods) && periods.length ? periods : SENTIMENT_PERIODS;

  effectivePeriods.forEach((period) => {
    const key = typeof period?.key === 'string' ? period.key : null;
    if (!key) {
      return;
    }
    if (!baseTime) {
      result.set(key, { value: null, classification: '', band: null });
      return;
    }
    const lookupTime = targetTime(baseTime, Number(period.lookbackDays ?? 0));
    let candidate = null;
    for (const point of timeline) {
      if (point.time > lookupTime) {
        break;
      }
      candidate = point;
    }
    if (!candidate) {
      result.set(key, { value: null, classification: '', band: null });
      return;
    }
    const rounded = Math.round(candidate.value);
    const band = resolveFearGreedBand(candidate.value);
    result.set(key, {
      value: rounded,
      classification: candidate.classification,
      band: band.slug,
    });
  });

  return result;
}

export function collectSnapshotElements(root = document) {
  if (!root) {
    return new Map();
  }
  let scope = null;
  if (typeof root.querySelectorAll === 'function' && root !== document) {
    scope = root;
  } else if (typeof root.getElementById === 'function') {
    scope = root.getElementById('fear-greed-snapshots');
  }
  if (!scope) {
    return new Map();
  }
  const entries = new Map();
  scope.querySelectorAll('[data-period]').forEach((node) => {
    const period = typeof node.dataset.period === 'string' ? node.dataset.period.trim() : '';
    if (!period) {
      return;
    }
    const valueEl = node.querySelector('[data-role="value"]');
    if (!valueEl) {
      return;
    }
    entries.set(period, { container: node, valueEl });
  });
  return entries;
}

export function renderSentimentSnapshots(elements, snapshots) {
  if (!(elements instanceof Map)) {
    return;
  }
  elements.forEach(({ valueEl }, key) => {
    if (!valueEl) {
      return;
    }
    const snapshot = snapshots instanceof Map ? snapshots.get(key) : null;
    if (!snapshot || snapshot.value === null) {
      valueEl.textContent = '—';
      if (valueEl.dataset) {
        delete valueEl.dataset.band;
      }
      valueEl.removeAttribute('title');
      return;
    }
    valueEl.textContent = String(snapshot.value);
    if (valueEl.dataset) {
      if (snapshot.band) {
        valueEl.dataset.band = snapshot.band;
      } else {
        delete valueEl.dataset.band;
      }
    }
    if (snapshot.classification) {
      valueEl.setAttribute('title', snapshot.classification);
    } else {
      valueEl.removeAttribute('title');
    }
  });
}

export function resetSentimentSnapshots(elements) {
  if (!(elements instanceof Map)) {
    return;
  }
  elements.forEach(({ valueEl }) => {
    if (!valueEl) {
      return;
    }
    valueEl.textContent = '—';
    if (valueEl.dataset) {
      delete valueEl.dataset.band;
    }
    valueEl.removeAttribute('title');
  });
}

export const __test__ = {
  normalizePoint,
  targetTime,
};

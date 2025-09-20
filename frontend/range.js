const DAY_MS = 24 * 60 * 60 * 1000;

export const RANGE_OPTIONS = [
  { key: '24h', label: '24h', durationMs: DAY_MS },
  { key: '7d', label: '7j', durationMs: 7 * DAY_MS },
  { key: '1m', label: '1m', durationMs: 30 * DAY_MS },
  { key: '3m', label: '3m', durationMs: 90 * DAY_MS },
  { key: '1y', label: '1 an', durationMs: 365 * DAY_MS },
  { key: '2y', label: '2 ans', durationMs: 2 * 365 * DAY_MS },
  { key: '5y', label: '5 ans', durationMs: 5 * 365 * DAY_MS },
  { key: 'max', label: 'Max', durationMs: Infinity },
];

function toTimestamp(value) {
  if (value instanceof Date) {
    const time = value.getTime();
    return Number.isFinite(time) ? time : null;
  }
  if (typeof value === 'number') {
    return Number.isFinite(value) ? value : null;
  }
  if (typeof value === 'string') {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const date = new Date(trimmed);
    const time = date.getTime();
    return Number.isFinite(time) ? time : null;
  }
  return null;
}

export function calculateAvailableRanges(timestamps = [], { now } = {}) {
  const normalized = (timestamps || [])
    .map((ts) => toTimestamp(ts))
    .filter((time) => typeof time === 'number');
  if (normalized.length === 0) {
    return new Set();
  }
  const latest = Math.max(...normalized);
  const earliest = Math.min(...normalized);
  const available = new Set();
  const nowTs = typeof now === 'number' && Number.isFinite(now) ? now : Date.now();

  RANGE_OPTIONS.forEach((option) => {
    if (option.key === 'max') {
      if (!available.has('max')) {
        available.add('max');
      }
      return;
    }
    if (!Number.isFinite(option.durationMs)) {
      return;
    }
    const span = latest - earliest;
    const hasCoverage = span >= option.durationMs;
    const hasRecentPoint = nowTs - latest <= Math.max(option.durationMs, DAY_MS);
    if (hasCoverage && hasRecentPoint) {
      available.add(option.key);
    }
  });

  if (!available.has('max')) {
    available.add('max');
  }

  return available;
}

export function pickInitialRange(available, desiredKey, options = RANGE_OPTIONS) {
  if (!(available instanceof Set) || available.size === 0) {
    return null;
  }
  if (desiredKey && available.has(desiredKey)) {
    return desiredKey;
  }
  const keys = options.map((opt) => opt.key);
  const desiredIndex = desiredKey ? keys.indexOf(desiredKey) : -1;
  if (desiredIndex >= 0) {
    for (let offset = 1; offset < keys.length; offset += 1) {
      const rightIndex = desiredIndex + offset;
      const leftIndex = desiredIndex - offset;
      const rightAvailable = rightIndex < keys.length && available.has(keys[rightIndex]);
      const leftAvailable = leftIndex >= 0 && available.has(keys[leftIndex]);
      if (rightAvailable) {
        return keys[rightIndex];
      }
      if (leftAvailable) {
        return keys[leftIndex];
      }
    }
  }
  for (const key of keys) {
    if (available.has(key)) {
      return key;
    }
  }
  return null;
}

export function syncRangeSelector(container, available) {
  if (!container) {
    return 0;
  }
  const set = available instanceof Set ? available : new Set();
  let visibleCount = 0;
  container.querySelectorAll('[data-range]').forEach((button) => {
    const { range } = button.dataset;
    const isAvailable = range ? set.has(range) : false;
    if (isAvailable) {
      button.hidden = false;
      button.disabled = false;
      button.removeAttribute('aria-hidden');
      button.removeAttribute('aria-disabled');
      button.removeAttribute('tabindex');
      visibleCount += 1;
    } else {
      button.hidden = true;
      button.disabled = true;
      button.setAttribute('aria-hidden', 'true');
      button.setAttribute('aria-disabled', 'true');
      button.setAttribute('tabindex', '-1');
      button.classList.remove('active');
      button.setAttribute('aria-pressed', 'false');
    }
  });
  container.hidden = visibleCount === 0;
  if (visibleCount === 0) {
    container.setAttribute('aria-hidden', 'true');
  } else {
    container.removeAttribute('aria-hidden');
  }
  return visibleCount;
}

export const __test__ = {
  toTimestamp,
};

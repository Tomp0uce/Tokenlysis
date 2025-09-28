import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { JSDOM } from 'jsdom';

import {
  evaluateRatios,
  evaluateFreshness,
  summarizeCategoryIssues,
  normalizeBudgetCategories,
} from '../frontend/debug.js';

function makeDiagPayload() {
  return {
    providers: {
      coinmarketcap: {
        base_url: 'https://pro-api.coinmarketcap.com',
        api_key_masked: '',
        fng_latest: {
          path: '/v3/fear-and-greed/latest',
          doc_url:
            'https://coinmarketcap.com/api/documentation/v3/#operation/getV3FearAndGreedLatest',
          safe_url: 'https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest',
        },
        fng_historical: {
          path: '/v3/fear-and-greed/historical',
          doc_url:
            'https://coinmarketcap.com/api/documentation/v3/#operation/getV3FearAndGreedHistorical',
          safe_url: 'https://pro-api.coinmarketcap.com/v3/fear-and-greed/historical',
        },
      },
      coingecko: {
        base_url: 'https://api.coingecko.com/api/v3',
        api_key_masked: '',
        markets: {
          path: '/coins/markets',
          doc_url: 'https://www.coingecko.com/en/api/documentation',
          safe_url: 'https://api.coingecko.com/api/v3/coins/markets?vs_currency=usd',
        },
      },
    },
    plan: 'demo',
    base_url: 'https://api.coingecko.com/api/v3',
    granularity: '12h',
    last_refresh_at: '2024-01-01T00:00:00Z',
    last_etl_items: 10,
    monthly_call_count: 5,
    monthly_call_categories: { markets: 5 },
    quota: 100,
    data_source: 'api',
    top_n: 200,
    fear_greed_last_refresh: '2024-01-01T00:00:00Z',
    fear_greed_count: 20,
    coingecko_usage: {
      plan: 'demo',
      monthly_call_count: 5,
      monthly_call_categories: { markets: 5 },
      quota: 100,
    },
    coinmarketcap_usage: {
      monthly_call_count: 0,
      monthly_call_categories: {},
      quota: 50,
      alert_threshold: 0.8,
    },
    fng_cache: {
      rows: 20,
      last_refresh: '2024-01-01T00:00:00Z',
      min_timestamp: '2023-12-01T00:00:00Z',
      max_timestamp: '2024-01-01T00:00:00Z',
    },
  };
}

function closeTo(value, expected, epsilon = 1e-6) {
  assert.ok(Math.abs(value - expected) <= epsilon, `${value} not within ${epsilon} of ${expected}`);
}

test('evaluateRatios returns normalized ratios and statuses', () => {
  const diag = {
    last_etl_items: 20,
    top_n: 20,
    monthly_call_count: 820,
    quota: 1000,
  };

  const metrics = evaluateRatios(diag);

  assert.equal(metrics.etl.status, 'ok');
  closeTo(metrics.etl.ratio, 1);
  assert.equal(metrics.budget.status, 'warn');
  closeTo(metrics.budget.ratio, 0.82);
});

test('evaluateRatios flags abnormal values and handles empty denominators', () => {
  const diag = {
    last_etl_items: 5,
    top_n: 20,
    monthly_call_count: 1200,
    quota: 0,
  };

  const metrics = evaluateRatios(diag);

  assert.equal(metrics.etl.status, 'error');
  closeTo(metrics.etl.ratio, 0.25);
  assert.equal(metrics.budget.status, 'unknown');
  assert.equal(metrics.budget.ratio, null);
});

test('evaluateFreshness reports ok when lag stays within the configured granularity', () => {
  const now = Date.UTC(2024, 0, 2, 0, 0, 0);
  const lastRefreshAt = new Date(now - 6 * 60 * 60 * 1000).toISOString();

  const metrics = evaluateFreshness({
    lastRefreshAt,
    granularity: '24h',
    stale: false,
    nowMs: now,
  });

  closeTo(metrics.differenceHours, 6);
  assert.equal(metrics.granularityHours, 24);
  closeTo(metrics.ratio, 0.25);
  assert.equal(metrics.status, 'ok');
});

test('evaluateFreshness escalates server-stale signals even when lag is small', () => {
  const now = Date.UTC(2024, 0, 2, 0, 0, 0);
  const lastRefreshAt = new Date(now - 2 * 60 * 60 * 1000).toISOString();

  const metrics = evaluateFreshness({
    lastRefreshAt,
    granularity: '24h',
    stale: true,
    nowMs: now,
  });

  assert.equal(metrics.status, 'error');
  closeTo(metrics.differenceHours, 2);
});

test('evaluateFreshness downgrades to warn when lag exceeds granularity but not by much', () => {
  const now = Date.UTC(2024, 0, 3, 12, 0, 0);
  const lastRefreshAt = new Date(now - 36 * 60 * 60 * 1000).toISOString();

  const metrics = evaluateFreshness({
    lastRefreshAt,
    granularity: '24h',
    stale: false,
    nowMs: now,
  });

  closeTo(metrics.differenceHours, 36);
  closeTo(metrics.granularityHours, 24);
  closeTo(metrics.ratio, 1.5);
  assert.equal(metrics.status, 'warn');
});

test('evaluateFreshness handles invalid timestamps gracefully', () => {
  const metrics = evaluateFreshness({
    lastRefreshAt: 'not-a-date',
    granularity: '24h',
    stale: false,
    nowMs: Date.UTC(2024, 0, 1, 0, 0, 0),
  });

  assert.equal(metrics.differenceHours, null);
  assert.equal(metrics.ratio, null);
  assert.equal(metrics.status, 'unknown');
});

test('summarizeCategoryIssues tallies missing and stale diagnostics', () => {
  const summary = summarizeCategoryIssues([
    { coin_id: 'a', reasons: ['missing_categories'] },
    { coin_id: 'b', reasons: ['stale_timestamp'] },
    { coin_id: 'c', reasons: ['missing_categories', 'stale_timestamp'] },
    { coin_id: 'd', reasons: [] },
  ]);

  assert.equal(summary.total, 4);
  assert.equal(summary.missing, 2);
  assert.equal(summary.stale, 2);
  assert.equal(summary.both, 1);
});

test('normalizeBudgetCategories sorts items and computes ratios', () => {
  const diag = {
    monthly_call_count: 10,
    monthly_call_categories: {
      markets: 6,
      coin_profile: 3,
      misc: 1,
    },
  };

  const breakdown = normalizeBudgetCategories(diag);

  assert.equal(breakdown.total, 10);
  assert.deepEqual(breakdown.categories, [
    { name: 'markets', count: 6, ratio: 0.6 },
    { name: 'coin_profile', count: 3, ratio: 0.3 },
    { name: 'misc', count: 1, ratio: 0.1 },
  ]);
});

test('normalizeBudgetCategories filters invalid inputs gracefully', () => {
  const breakdown = normalizeBudgetCategories({
    monthly_call_count: '12',
    monthly_call_categories: {
      markets: 5,
      stale: -2,
      weird: 'oops',
    },
  });

  assert.equal(breakdown.total, 12);
  assert.deepEqual(breakdown.categories, [
    { name: 'markets', count: 5, ratio: 5 / 12 },
  ]);
});

test('debug page exposes a theme toggle control for accessibility', () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const dom = new JSDOM(html);
  const toggle = dom.window.document.querySelector('[data-theme-toggle]');
  assert.ok(toggle, 'theme toggle should exist on debug page');
  assert.equal(toggle.getAttribute('type'), 'button');
  assert.equal(toggle.classList.contains('theme-toggle'), true);
  const providers = dom.window.document.getElementById('providers-list');
  assert.ok(providers, 'providers list placeholder should exist');
});

test('debug page exposes a refresh button for API usage', () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const dom = new JSDOM(html);
  const refresh = dom.window.document.querySelector('[data-role="refresh-usage"]');
  assert.ok(refresh, 'refresh usage button should exist');
  assert.equal(refresh?.getAttribute('type'), 'button');
});

test('debug initialization reuses stored theme preference', async () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const dom = new JSDOM(html, { url: 'http://localhost' });

  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });
  global.fetch = async (url) => {
    if (url.endsWith('/diag')) {
      return { ok: true, status: 200, json: async () => makeDiagPayload() };
    }
    if (url.endsWith('/markets/top?limit=1')) {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    if (url.endsWith('/debug/categories')) {
      return { ok: true, status: 200, json: async () => ({ items: [] }) };
    }
    throw new Error(`Unexpected fetch ${url}`);
  };

  localStorage.setItem('tokenlysis-theme', 'dark');

  try {
    const module = await import('../frontend/debug.js');

    await module.initializeDebugPage();

    const toggle = document.querySelector('[data-theme-toggle]');
    assert.equal(document.documentElement.dataset.theme, 'dark');
    assert.equal(toggle?.dataset.themeState, 'dark');
    assert.equal(toggle?.getAttribute('aria-checked'), 'true');
  } finally {
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  }
});

test('debug page renders provider diagnostics with safe links', async () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const dom = new JSDOM(html, { url: 'http://localhost' });

  global.window = dom.window;
  global.document = dom.window.document;
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });

  const diagPayload = makeDiagPayload();
  global.fetch = async (url) => {
    if (url.endsWith('/diag')) {
      return { ok: true, status: 200, json: async () => diagPayload };
    }
    if (url.endsWith('/markets/top?limit=1')) {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    if (url.endsWith('/debug/categories')) {
      return { ok: true, status: 200, json: async () => ({ items: [] }) };
    }
    throw new Error(`Unexpected fetch ${url}`);
  };

  try {
    const module = await import('../frontend/debug.js');
    await module.loadDiagnostics();

    const providers = document.querySelectorAll('[data-provider]');
    assert.equal(providers.length, 2);

    const cmc = document.querySelector('[data-provider="coinmarketcap"]');
    assert.ok(cmc);
    const cmcBase = cmc.querySelector('[data-role="base-url"]');
    assert.equal(cmcBase?.textContent, diagPayload.providers.coinmarketcap.base_url);
    const cmcDoc = cmc.querySelector('a[data-role="doc-link"]');
    assert.equal(cmcDoc?.getAttribute('href'), diagPayload.providers.coinmarketcap.fng_latest.doc_url);
    const cmcSafe = cmc.querySelector('a[data-role="safe-link"]');
    assert.equal(
      cmcSafe?.getAttribute('href'),
      diagPayload.providers.coinmarketcap.fng_latest.safe_url,
    );
    const cmcKey = cmc.querySelector('[data-role="masked-key"]');
    assert.equal(cmcKey?.textContent, '');

    const cg = document.querySelector('[data-provider="coingecko"]');
    assert.ok(cg);
    const cgSafe = cg.querySelector('a[data-role="safe-link"]');
    assert.equal(
      cgSafe?.getAttribute('href'),
      diagPayload.providers.coingecko.markets.safe_url,
    );
  } finally {
    delete global.window;
    delete global.document;
    delete global.fetch;
  }
});

test('renderDiag updates optional CoinMarketCap metrics when placeholders exist', async () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const dom = new JSDOM(html, { url: 'http://localhost' });

  global.window = dom.window;
  global.document = dom.window.document;
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });

  const cmcWrapper = document.createElement('section');
  cmcWrapper.id = 'cmc-diagnostics';
  const cmcCount = document.createElement('span');
  cmcCount.id = 'cmc-budget-count';
  const cmcQuota = document.createElement('span');
  cmcQuota.id = 'cmc-budget-quota';
  const cmcRatio = document.createElement('span');
  cmcRatio.id = 'cmc-budget-ratio';
  cmcRatio.classList.add('status-pill');
  const cmcList = document.createElement('ul');
  cmcList.id = 'cmc-budget-breakdown-list';
  cmcWrapper.append(cmcCount, cmcQuota, cmcRatio, cmcList);
  document.body.appendChild(cmcWrapper);

  const diagPayload = makeDiagPayload();
  diagPayload.coinmarketcap_usage.monthly_call_count = 26;
  diagPayload.coinmarketcap_usage.quota = 30;
  diagPayload.coinmarketcap_usage.monthly_call_categories = {
    latest: 20,
    history: 6,
  };

  global.fetch = async (url) => {
    if (url.endsWith('/diag')) {
      return { ok: true, status: 200, json: async () => diagPayload };
    }
    if (url.endsWith('/markets/top?limit=1')) {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    if (url.endsWith('/debug/categories')) {
      return { ok: true, status: 200, json: async () => ({ items: [] }) };
    }
    throw new Error(`Unexpected fetch ${url}`);
  };

  try {
    const module = await import('../frontend/debug.js');
    await module.loadDiagnostics();

    assert.equal(document.getElementById('cmc-budget-count')?.textContent, '26');
    assert.equal(document.getElementById('cmc-budget-quota')?.textContent, '30');
    const ratioEl = document.getElementById('cmc-budget-ratio');
    assert.ok(ratioEl?.classList.contains('status-pill'));
    assert.equal(ratioEl?.textContent, '86,7 %');
    assert.equal(ratioEl?.classList.contains('status-warn'), true);

    const items = Array.from(document.querySelectorAll('#cmc-budget-breakdown-list li'));
    assert.equal(items.length, 2);
    assert.equal(items[0]?.textContent, 'Latest : 20 — 76,9 %');
    assert.equal(items[1]?.textContent, 'History : 6 — 23,1 %');
  } finally {
    delete global.window;
    delete global.document;
    delete global.fetch;
  }
});

test('usage refresh button fetches live quotas and updates metrics', async () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const dom = new JSDOM(html, { url: 'http://localhost' });

  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });

  const usageCalls = [];
  const diagPayload = makeDiagPayload();
  const usagePayload = {
    coingecko: {
      monthly_call_count: 120,
      quota: 1000,
      plan: 'pro',
    },
    coinmarketcap: {
      monthly_call_count: 320,
      quota: 5000,
      monthly: {
        credits_used: 320,
        credits_left: 4680,
        quota: 5000,
      },
    },
  };

  global.fetch = async (url, options = {}) => {
    if (url.endsWith('/diag')) {
      return { ok: true, status: 200, json: async () => diagPayload };
    }
    if (url.endsWith('/markets/top?limit=1')) {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    if (url.endsWith('/debug/categories')) {
      return { ok: true, status: 200, json: async () => ({ items: [] }) };
    }
    if (url.endsWith('/diag/refresh-usage')) {
      usageCalls.push(options);
      return { ok: true, status: 200, json: async () => usagePayload };
    }
    throw new Error(`Unexpected fetch ${url}`);
  };

  try {
    const module = await import('../frontend/debug.js');
    await module.initializeDebugPage();

    const refresh = document.querySelector('[data-role="refresh-usage"]');
    assert.ok(refresh);
    refresh.click();

    await new Promise((resolve) => setTimeout(resolve, 0));

    assert.equal(usageCalls.length, 1);
    assert.equal(usageCalls[0]?.method ?? 'GET', 'POST');
    assert.equal(document.getElementById('budget-count')?.textContent, '120');
    assert.equal(document.getElementById('budget-quota')?.textContent, '1 000');
    assert.equal(document.getElementById('budget-ratio')?.textContent, '12,0 %');
    assert.equal(document.getElementById('cmc-budget-count')?.textContent, '320');
    assert.equal(document.getElementById('cmc-budget-quota')?.textContent, '5 000');
    assert.equal(document.getElementById('cmc-budget-ratio')?.textContent, '6,4 %');
    assert.equal(refresh?.disabled, false);
  } finally {
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  }
});

test('usage refresh button reports errors and re-enables control', async () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const dom = new JSDOM(html, { url: 'http://localhost' });

  global.window = dom.window;
  global.document = dom.window.document;
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });

  const diagPayload = makeDiagPayload();
  let refreshAttempts = 0;

  global.fetch = async (url) => {
    if (url.endsWith('/diag')) {
      return { ok: true, status: 200, json: async () => diagPayload };
    }
    if (url.endsWith('/markets/top?limit=1')) {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    if (url.endsWith('/debug/categories')) {
      return { ok: true, status: 200, json: async () => ({ items: [] }) };
    }
    if (url.endsWith('/diag/refresh-usage')) {
      refreshAttempts += 1;
      return { ok: false, status: 500, json: async () => ({}) };
    }
    throw new Error(`Unexpected fetch ${url}`);
  };

  try {
    const module = await import('../frontend/debug.js');
    await module.initializeDebugPage();

    const refresh = document.querySelector('[data-role="refresh-usage"]');
    refresh?.click();
    await new Promise((resolve) => setTimeout(resolve, 0));

    const status = document.getElementById('diag-status');
    assert.ok(status?.textContent?.includes('Erreur lors de la mise à jour des crédits'));
    assert.equal(refresh?.disabled, false);
    assert.equal(refreshAttempts, 1);
  } finally {
    delete global.window;
    delete global.document;
    delete global.fetch;
  }
});

test('providers grid collapses to a single column on small screens', () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');

  assert.match(
    html,
    /@media\s*\(max-width:\s*600px\)[\s\S]*\.providers-grid\s*{[\s\S]*grid-template-columns:\s*1fr/i,
    'providers grid should switch to single column at mobile breakpoint',
  );
});

test('provider rendering tolerates endpoints without documentation links', async () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const dom = new JSDOM(html, { url: 'http://localhost' });

  global.window = dom.window;
  global.document = dom.window.document;
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });

  const diagPayload = makeDiagPayload();
  diagPayload.providers.coinmarketcap.fng_latest = {
    path: '/v3/fear-and-greed/latest',
    safe_url: 'https://pro-api.coinmarketcap.com/v3/fear-and-greed/latest',
  };
  diagPayload.providers.coinmarketcap.fng_historical = {
    path: '/v3/fear-and-greed/historical',
  };

  global.fetch = async (url) => {
    if (url.endsWith('/diag')) {
      return { ok: true, status: 200, json: async () => diagPayload };
    }
    if (url.endsWith('/markets/top?limit=1')) {
      return { ok: true, status: 200, json: async () => ({}) };
    }
    if (url.endsWith('/debug/categories')) {
      return { ok: true, status: 200, json: async () => ({ items: [] }) };
    }
    throw new Error(`Unexpected fetch ${url}`);
  };

  try {
    const module = await import('../frontend/debug.js');
    await module.loadDiagnostics();

    const cmcCard = document.querySelector('[data-provider="coinmarketcap"]');
    assert.ok(cmcCard, 'coinmarketcap card should exist');
    const endpointItems = cmcCard?.querySelectorAll('.provider-endpoints li');
    assert.equal(endpointItems?.length, 2, 'should render one entry per endpoint');

    const firstItem = endpointItems?.[0];
    const docLink = firstItem?.querySelector('a[data-role="doc-link"]');
    assert.equal(docLink, null, 'should not render documentation link when missing');
    const safeLink = firstItem?.querySelector('a[data-role="safe-link"]');
    assert.ok(safeLink, 'safe link should be rendered when provided');

    const secondItem = endpointItems?.[1];
    assert.equal(
      secondItem?.querySelectorAll('a').length,
      0,
      'endpoints without safe URLs should not render anchor tags',
    );
  } finally {
    delete global.window;
    delete global.document;
    delete global.fetch;
  }
});

test('debug styles rely on theme tokens for surfaces and text', () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const html = fs.readFileSync(htmlPath, 'utf8');
  assert.match(html, /body\s*{[\s\S]*background:\s*var\(--surface-base\)[\s\S]*color:\s*var\(--text-primary\)/);
  assert.match(html, /\.metric-card\s*{[\s\S]*background:\s*var\(--surface-card\)/);
  assert.match(html, /\.metric-values\s*{[\s\S]*color:\s*var\(--text-muted\)/);
});

test('status pills use dedicated theme variables for contrast in light and dark modes', () => {
  const htmlPath = path.join('frontend', 'debug.html');
  const cssPath = path.join('frontend', 'theme.css');
  const html = fs.readFileSync(htmlPath, 'utf8');
  const css = fs.readFileSync(cssPath, 'utf8');

  assert.match(css, /:root\s*{[\s\S]*--status-ok-bg:[^;]+;[\s\S]*--status-ok-text:[^;]+;/);
  assert.match(css, /:root\s*{[\s\S]*--status-warn-bg:[^;]+;[\s\S]*--status-warn-text:[^;]+;/);
  assert.match(css, /:root\s*{[\s\S]*--status-error-bg:[^;]+;[\s\S]*--status-error-text:[^;]+;/);
  assert.match(css, /:root\s*{[\s\S]*--status-unknown-bg:[^;]+;[\s\S]*--status-unknown-text:[^;]+;/);

  assert.match(css, /:root\[data-theme='dark'\][\s\S]*--status-ok-bg:[^;]+;[\s\S]*--status-ok-text:[^;]+;/);
  assert.match(css, /:root\[data-theme='dark'\][\s\S]*--status-warn-bg:[^;]+;[\s\S]*--status-warn-text:[^;]+;/);
  assert.match(css, /:root\[data-theme='dark'\][\s\S]*--status-error-bg:[^;]+;[\s\S]*--status-error-text:[^;]+;/);
  assert.match(css, /:root\[data-theme='dark'\][\s\S]*--status-unknown-bg:[^;]+;[\s\S]*--status-unknown-text:[^;]+;/);

  assert.match(html, /\.status-ok\s*{[\s\S]*background:\s*var\(--status-ok-bg\)[\s\S]*color:\s*var\(--status-ok-text\)/);
  assert.match(html, /\.status-warn\s*{[\s\S]*background:\s*var\(--status-warn-bg\)[\s\S]*color:\s*var\(--status-warn-text\)/);
  assert.match(html, /\.status-error\s*{[\s\S]*background:\s*var\(--status-error-bg\)[\s\S]*color:\s*var\(--status-error-text\)/);
  assert.match(html, /\.status-unknown\s*{[\s\S]*background:\s*var\(--status-unknown-bg\)[\s\S]*color:\s*var\(--status-unknown-text\)/);
});

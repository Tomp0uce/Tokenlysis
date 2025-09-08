import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';
import { extractItems, formatDiag, formatMeta, resolveVersion } from '../frontend/utils.js';

// T1: extractItems with array input returns same array

test('extractItems returns array when json is array', () => {
  const arr = [{ id: 1 }, { id: 2 }];
  assert.deepEqual(extractItems(arr), arr);
});

// T2: extractItems with object containing items returns items array

test('extractItems returns json.items when json has items array', () => {
  const json = { items: [{ id: 3 }] };
  assert.deepEqual(extractItems(json), json.items);
});

// T3: extractItems throws on missing items

test('extractItems throws on invalid schema', () => {
  assert.throws(() => extractItems({ foo: [] }), /Invalid schema: missing 'items'/);
});

// T4: formatDiag uses unknown values when data missing

test('formatDiag falls back to unknown', () => {
  const lr = { url: '/x', status: 200, latency: 1 };
  assert.match(
    formatDiag(lr, null),
    /plan=unknown \| granularity=unknown \| last_etl_items=unknown/
  );
});

// T5: formatMeta renders metadata with stale badge

test('formatMeta renders metadata with stale badge', () => {
  const marketMeta = {
    last_refresh_at: '2025-09-07T20:51:26Z',
    data_source: 'api',
    stale: true,
  };
  const diagMeta = { plan: 'demo', last_etl_items: 50 };
  const html = formatMeta(marketMeta, diagMeta);
  assert.match(html, /Plan: demo/);
  assert.match(html, /Last refresh: 20:51Z/);
  assert.match(html, /Source: api/);
  assert.match(html, /Items: 50/);
  assert.match(html, /<span class="badge">stale<\/span>/);
});

// T6: formatMeta omits stale badge when not stale

test('formatMeta omits stale badge when not stale', () => {
  const marketMeta = {
    last_refresh_at: '2025-09-07T20:51:26Z',
    data_source: 'api',
    stale: false,
  };
  const diagMeta = { plan: 'demo', last_etl_items: 50 };
  const html = formatMeta(marketMeta, diagMeta);
  assert.doesNotMatch(html, /badge/);
});

// T7: resolveVersion prefers API version over local dev

test('resolveVersion prefers API version over local', () => {
  assert.equal(resolveVersion('1.2.3', 'dev'), '1.2.3');
});

// T8: resolveVersion falls back to local when API version missing

test('resolveVersion falls back to local', () => {
  assert.equal(resolveVersion(null, '2.0.0'), '2.0.0');
});

// T9: resolveVersion defaults to dev when both missing

test('resolveVersion defaults to dev', () => {
  assert.equal(resolveVersion(null, null), 'dev');
});

// DOM Tests

function setupDom() {
  const dom = new JSDOM(`<!DOCTYPE html><meta name="api-url" content="">\n<div id="demo-banner" style="display:none"></div>\n<div id="status"></div>\n<table id="cryptos" style="display:none"><thead><tr><th>Coin</th><th>Rank</th><th>Price</th><th>Market Cap</th><th>Volume 24h</th><th>Change 24h</th></tr></thead><tbody></tbody></table>\n<div id="meta"></div>\n<div id="version"></div>\n<div id="diag"></div>\n<div id="debug-panel"></div>`);
  global.window = dom.window;
  global.document = dom.window.document;
  return dom;
}

test('loadCryptos renders table and diagnostics', async () => {
  setupDom();
  const { loadCryptos, loadVersion } = await import('../frontend/main.js');
  const markets = {
    items: [
      {
        coin_id: 'bitcoin',
        rank: 1,
        price: 1,
        market_cap: 2,
        volume_24h: 3,
        pct_change_24h: 4,
      },
    ],
    last_refresh_at: '2025-09-07T20:51:26Z',
    stale: false,
    data_source: 'api',
  };
  const diag = {
    plan: 'demo',
    granularity: '12h',
    last_refresh_at: '2025-09-07T20:51:26Z',
    last_etl_items: 50,
    monthly_call_count: 1,
    quota: 10000,
    data_source: 'api',
    top_n: 50,
  };
  const lastReq = { endpoint: '/coins/markets', status: 200 };
  global.fetch = async (url) => {
    if (url.endsWith('/markets/top?limit=20&vs=usd')) {
      return new Response(JSON.stringify(markets), { status: 200 });
    }
    if (url.endsWith('/diag')) {
      return new Response(JSON.stringify(diag), { status: 200 });
    }
    if (url.endsWith('/debug/last-request')) {
      return new Response(JSON.stringify(lastReq), { status: 200 });
    }
    if (url.endsWith('/version')) {
      return new Response(JSON.stringify({ version: '1.0.0' }), { status: 200 });
    }
    throw new Error('unexpected fetch ' + url);
  };

  await loadVersion();
  await loadCryptos();

  const cells = [...document.querySelectorAll('#cryptos tbody tr td')].map((c) => c.textContent);
  assert.deepEqual(cells, ['bitcoin', '1', '1.00', '2', '3', '4.00%']);
  assert.match(document.getElementById('diag').textContent, /plan=demo/);
  assert.match(document.getElementById('debug-panel').textContent, /plan=demo/);
});

test('loadCryptos tolerates diag failure', async () => {
  setupDom();
  const { loadCryptos, loadVersion } = await import('../frontend/main.js');
  const markets = {
    items: [
      {
        coin_id: 'bitcoin',
        rank: 1,
        price: 1,
        market_cap: 2,
        volume_24h: 3,
        pct_change_24h: 4,
      },
    ],
    last_refresh_at: '2025-09-07T20:51:26Z',
    stale: false,
    data_source: 'api',
  };
  const lastReq = { endpoint: '/coins/markets', status: 200 };
  global.fetch = async (url) => {
    if (url.endsWith('/markets/top?limit=20&vs=usd')) {
      return new Response(JSON.stringify(markets), { status: 200 });
    }
    if (url.endsWith('/diag')) {
      return new Response('oops', { status: 500 });
    }
    if (url.endsWith('/debug/last-request')) {
      return new Response(JSON.stringify(lastReq), { status: 200 });
    }
    if (url.endsWith('/version')) {
      return new Response(JSON.stringify({ version: '1.0.0' }), { status: 200 });
    }
    throw new Error('unexpected fetch ' + url);
  };

  await loadVersion();
  await loadCryptos();

  const firstCell = document.querySelector('#cryptos tbody tr td').textContent;
  assert.equal(firstCell, 'bitcoin');
  assert.match(document.getElementById('diag').textContent, /plan=unknown/);
});

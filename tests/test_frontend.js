import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';
import { extractItems, resolveVersion } from '../frontend/utils.js';

// Utility tests

test('extractItems returns array when json is array', () => {
  const arr = [{ id: 1 }, { id: 2 }];
  assert.deepEqual(extractItems(arr), arr);
});

test('extractItems returns json.items when json has items array', () => {
  const json = { items: [{ id: 3 }] };
  assert.deepEqual(extractItems(json), json.items);
});

test('extractItems throws on invalid schema', () => {
  assert.throws(() => extractItems({ foo: [] }), /Invalid schema: missing 'items'/);
});

test('resolveVersion prefers API version over local', () => {
  assert.equal(resolveVersion('1.2.3', 'dev'), '1.2.3');
});

test('resolveVersion falls back to local when API missing', () => {
  assert.equal(resolveVersion(null, '2.0.0'), '2.0.0');
});

test('resolveVersion defaults to dev when both missing', () => {
  assert.equal(resolveVersion(null, null), 'dev');
});

function setupDom() {
  const dom = new JSDOM(`<!DOCTYPE html><meta name="api-url" content="">
    <div id="demo-banner" style="display:none"></div>
    <div id="status"></div>
    <table id="cryptos" style="display:none"><thead><tr><th>Coin</th><th>Catégories</th><th>Rank</th><th>Price</th><th>Market Cap</th><th>Volume 24h</th><th>Change 24h</th></tr></thead><tbody></tbody></table>
    <div id="last-update"></div>
    <div id="version"></div>`);
  global.window = dom.window;
  global.document = dom.window.document;
  return dom;
}

test('loadCryptos renders table and last update with categories', async () => {
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
        category_names: ['Layer 1', 'DeFi', 'NFT', 'Payments'],
        category_ids: ['layer-1', 'defi', 'nft', 'payments'],
      },
      {
        coin_id: 'nocat',
        rank: 2,
        price: 0.5,
        market_cap: 1,
        volume_24h: 1,
        pct_change_24h: 0,
        category_names: [],
        category_ids: [],
      },
    ],
    last_refresh_at: '2025-09-07T20:51:26Z',
    data_source: 'api',
  };
  global.fetch = async (url) => {
    if (url.endsWith('/markets/top?limit=20&vs=usd')) {
      return new Response(JSON.stringify(markets), { status: 200 });
    }
    if (url.endsWith('/version')) {
      return new Response(JSON.stringify({ version: '1.0.0' }), { status: 200 });
    }
    if (url.endsWith('/diag')) {
      return new Response(JSON.stringify({ plan: 'demo' }), { status: 200 });
    }
    throw new Error('unexpected fetch ' + url);
  };
  await loadVersion();
  await loadCryptos();
  const rows = [...document.querySelectorAll('#cryptos tbody tr')];
  const cells1 = [...rows[0].querySelectorAll('td')].map((c) => c.textContent.trim().replace(/\s+/g, ' '));
  assert.deepEqual(cells1, ['bitcoin', 'Layer 1 DeFi NFT +1', '1', '1.00', '2', '3', '4.00%']);
  const cells2 = [...rows[1].querySelectorAll('td')].map((c) => c.textContent.trim());
  assert.deepEqual(cells2, ['nocat', '', '2', '0.5000', '1', '1', '0.00%']);
  assert.equal(document.getElementById('demo-banner').style.display, 'block');
  assert.match(
    document.getElementById('last-update').textContent,
    /Dernière mise à jour : 2025-09-07T20:51:26Z \(source: api\)/
  );
});

test('loadCryptos hides demo banner when plan is not demo', async () => {
  setupDom();
  const { loadCryptos } = await import('../frontend/main.js');
  const markets = { items: [], last_refresh_at: null, data_source: null };
  global.fetch = async (url) => {
    if (url.endsWith('/markets/top?limit=20&vs=usd')) {
      return new Response(JSON.stringify(markets), { status: 200 });
    }
    if (url.endsWith('/diag')) {
      return new Response(JSON.stringify({ plan: 'pro' }), { status: 200 });
    }
    throw new Error('unexpected fetch ' + url);
  };
  await loadCryptos();
  assert.equal(document.getElementById('demo-banner').style.display, 'none');
});

test('loadCryptos handles failure', async () => {
  setupDom();
  const { loadCryptos } = await import('../frontend/main.js');
  global.fetch = async () => new Response('oops', { status: 500 });
  await loadCryptos();
  assert.match(document.getElementById('status').innerHTML, /Error fetching data/);
});

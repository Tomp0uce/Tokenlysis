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
    <table id="cryptos" style="display:none"><thead><tr><th>Coin</th><th>Catégories</th><th>Rank</th><th>Price</th><th>Market Cap</th><th>Fully Diluted Market Cap</th><th>Volume 24h</th><th>Change 24h</th><th>Change 7j</th><th>Change 30j</th></tr></thead><tbody></tbody></table>
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
        fully_diluted_market_cap: 3,
        volume_24h: 3,
        pct_change_24h: 4,
        pct_change_7d: 5,
        pct_change_30d: 6,
        category_names: ['Layer 1', 'DeFi', 'NFT', 'Payments'],
        category_ids: ['layer-1', 'defi', 'nft', 'payments'],
      },
      {
        coin_id: 'nocat',
        rank: 2,
        price: 0.5,
        market_cap: 1,
        fully_diluted_market_cap: 1.5,
        volume_24h: 1,
        pct_change_24h: -2,
        pct_change_7d: -3.25,
        pct_change_30d: -10,
        category_names: [],
        category_ids: [],
      },
      {
        coin_id: 'flat',
        rank: 3,
        price: 2,
        market_cap: 2,
        fully_diluted_market_cap: null,
        volume_24h: 0,
        pct_change_24h: 0,
        pct_change_7d: null,
        pct_change_30d: 0,
        category_names: ['Utility'],
        category_ids: ['utility'],
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
  assert.equal(rows.length, 3);
  const cells1 = [...rows[0].querySelectorAll('td')].map((c) => c.textContent.trim().replace(/\s+/g, ' '));
  assert.deepEqual(cells1, [
    'bitcoin',
    'Layer 1 DeFi NFT +1',
    '1',
    '1.00',
    '2',
    '3',
    '3',
    '4.00%',
    '5.00%',
    '6.00%',
  ]);
  const badges = rows[0].querySelectorAll('td')[1].querySelectorAll('.badge');
  assert.equal(badges[0].getAttribute('title'), 'Layer 1');
  assert.equal(badges[3].getAttribute('title'), 'Payments');
  const cells2 = [...rows[1].querySelectorAll('td')].map((c) => c.textContent.trim());
  assert.deepEqual(cells2, [
    'nocat',
    '',
    '2',
    '0.5000',
    '1',
    '1.5',
    '1',
    '-2.00%',
    '-3.25%',
    '-10.00%',
  ]);
  assert.equal(rows[1].querySelectorAll('td')[1].children.length, 0);
  const cells3 = [...rows[2].querySelectorAll('td')].map((c) => c.textContent.trim());
  assert.deepEqual(cells3, [
    'flat',
    'Utility',
    '3',
    '2.00',
    '2',
    '',
    '0',
    '0.00%',
    '',
    '0.00%',
  ]);
  const changeCellsRow1 = rows[0].querySelectorAll('.change-cell');
  assert.equal(changeCellsRow1.length, 3);
  changeCellsRow1.forEach((cell) => {
    assert.equal(cell.classList.contains('change-positive'), true);
    assert.equal(cell.classList.contains('change-negative'), false);
  });
  const changeCellsRow2 = rows[1].querySelectorAll('.change-cell');
  assert.equal(changeCellsRow2.length, 3);
  changeCellsRow2.forEach((cell) => {
    assert.equal(cell.classList.contains('change-positive'), false);
    assert.equal(cell.classList.contains('change-negative'), true);
  });
  const changeCellsRow3 = rows[2].querySelectorAll('.change-cell');
  assert.equal(changeCellsRow3.length, 3);
  changeCellsRow3.forEach((cell, idx) => {
    if (idx === 1) {
      assert.equal(cell.textContent.trim(), '');
    }
    assert.equal(cell.classList.contains('change-positive'), false);
    assert.equal(cell.classList.contains('change-negative'), false);
  });
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

test('clicking rank header toggles ascending then descending order', async () => {
  setupDom();
  const { loadCryptos } = await import('../frontend/main.js');
  const markets = {
    items: [
      {
        coin_id: 'beta',
        rank: 2,
        price: 10,
        market_cap: 3,
        fully_diluted_market_cap: 4,
        volume_24h: 5,
        pct_change_24h: -1,
        pct_change_7d: -2,
        pct_change_30d: -3,
        category_names: [],
        category_ids: [],
      },
      {
        coin_id: 'delta',
        rank: 4,
        price: 20,
        market_cap: 2,
        fully_diluted_market_cap: 3,
        volume_24h: 4,
        pct_change_24h: 6,
        pct_change_7d: 7,
        pct_change_30d: 8,
        category_names: [],
        category_ids: [],
      },
      {
        coin_id: 'alpha',
        rank: 1,
        price: 30,
        market_cap: 1,
        fully_diluted_market_cap: 2,
        volume_24h: 3,
        pct_change_24h: 9,
        pct_change_7d: 10,
        pct_change_30d: 11,
        category_names: [],
        category_ids: [],
      },
    ],
    last_refresh_at: null,
    data_source: null,
  };
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

  const ranks = () =>
    [...document.querySelectorAll('#cryptos tbody tr')].map((row) =>
      Number(row.querySelectorAll('td')[2].textContent)
    );
  assert.deepEqual(ranks(), [2, 4, 1]);

  const rankHeader = document.querySelectorAll('#cryptos thead th')[2];
  rankHeader.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.deepEqual(ranks(), [1, 2, 4]);

  rankHeader.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.deepEqual(ranks(), [4, 2, 1]);
});

test('sorting numeric columns keeps null values at the end', async () => {
  setupDom();
  const { loadCryptos } = await import('../frontend/main.js');
  const markets = {
    items: [
      {
        coin_id: 'null-price',
        rank: 1,
        price: null,
        market_cap: 3,
        fully_diluted_market_cap: 5,
        volume_24h: 7,
        pct_change_24h: null,
        pct_change_7d: 2,
        pct_change_30d: 3,
        category_names: [],
        category_ids: [],
      },
      {
        coin_id: 'negative',
        rank: 2,
        price: -3,
        market_cap: 2,
        fully_diluted_market_cap: null,
        volume_24h: 5,
        pct_change_24h: -5,
        pct_change_7d: -1,
        pct_change_30d: -2,
        category_names: [],
        category_ids: [],
      },
      {
        coin_id: 'positive',
        rank: 3,
        price: 15,
        market_cap: 1,
        fully_diluted_market_cap: 2,
        volume_24h: null,
        pct_change_24h: 4,
        pct_change_7d: 6,
        pct_change_30d: 8,
        category_names: [],
        category_ids: [],
      },
    ],
    last_refresh_at: null,
    data_source: null,
  };
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

  const priceHeader = document.querySelectorAll('#cryptos thead th')[3];
  priceHeader.dispatchEvent(new window.Event('click', { bubbles: true }));
  let order = [...document.querySelectorAll('#cryptos tbody tr')].map((row) =>
    row.querySelectorAll('td')[0].textContent.trim()
  );
  assert.deepEqual(order, ['negative', 'positive', 'null-price']);

  priceHeader.dispatchEvent(new window.Event('click', { bubbles: true }));
  order = [...document.querySelectorAll('#cryptos tbody tr')].map((row) =>
    row.querySelectorAll('td')[0].textContent.trim()
  );
  assert.deepEqual(order, ['positive', 'negative', 'null-price']);
});

test('selectedCategories defaults to empty array', async () => {
  const { selectedCategories } = await import('../frontend/main.js');
  assert.deepEqual(selectedCategories, []);
});

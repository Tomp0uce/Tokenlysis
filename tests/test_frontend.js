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
  const dom = new JSDOM(
    `<!DOCTYPE html><meta name="api-url" content="https://example.test/api">
    <div id="demo-banner" style="display:none"></div>
    <div id="status"></div>
    <div class="summary-grid">
      <article class="summary-card">
        <div class="summary-card-header">
          <span>Capitalisation totale</span>
          <strong id="summary-market-cap">—</strong>
        </div>
        <ul class="summary-card-metrics">
          <li class="summary-metric"><span class="summary-metric-label">Var. 24h</span><span id="summary-market-cap-change-24h" class="summary-change-value">—</span></li>
          <li class="summary-metric"><span class="summary-metric-label">Var. 7j</span><span id="summary-market-cap-change-7d" class="summary-change-value">—</span></li>
        </ul>
      </article>
      <article class="summary-card">
        <div class="summary-card-header">
          <span>Volume total</span>
          <strong id="summary-volume">—</strong>
        </div>
        <ul class="summary-card-metrics">
          <li class="summary-metric"><span class="summary-metric-label">Var. 24h</span><span id="summary-volume-change-24h" class="summary-change-value">—</span></li>
          <li class="summary-metric"><span class="summary-metric-label">Var. 7j</span><span id="summary-volume-change-7d" class="summary-change-value">—</span></li>
        </ul>
      </article>
    </div>
    <div class="table-controls pagination-controls" id="market-pagination" data-pagination hidden>
      <p class="pagination-info" data-role="pagination-info"></p>
      <div class="pagination-actions">
        <button type="button" data-role="pagination-prev">Précédent</button>
        <div class="pagination-pages" data-role="pagination-pages"></div>
        <button type="button" data-role="pagination-next">Suivant</button>
      </div>
    </div>
    <table id="cryptos" style="display:none"><thead><tr><th>Coin</th><th>Catégories</th><th>Rank</th><th>Price</th><th>Market Cap</th><th>Fully Diluted Market Cap</th><th>Volume 24h</th><th>Change 24h</th><th>Change 7j</th><th>Change 30j</th><th>Détails</th></tr></thead><tbody></tbody></table>
    <div id="market-overview-chart"></div>
    <div id="last-update"></div>
    <div id="version"></div>`,
    { url: 'https://example.test/' },
  );
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  class ApexChartsStub {
    constructor(element, options) {
      this.element = element;
      this.options = options;
    }
    render() {
      return Promise.resolve();
    }
    updateOptions() {
      return Promise.resolve();
    }
    updateSeries() {
      return Promise.resolve();
    }
  }
  dom.window.ApexCharts = ApexChartsStub;
  return dom;
}

function mockApiFetch(
  items,
  {
    diagPlan = 'pro',
    version,
    lastRefreshAt = '2024-01-01T00:00:00Z',
    dataSource = 'CoinGecko API',
    failMarkets = false,
    marketsStatus = 500,
  } = {},
) {
  const payload = {
    items: Array.isArray(items) ? items : [],
    last_refresh_at: lastRefreshAt,
    data_source: dataSource,
    stale: false,
  };

  return async (url) => {
    if (url.startsWith('https://example.test/api/markets/top')) {
      if (failMarkets) {
        return new Response('error', { status: marketsStatus });
      }
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url.startsWith('https://example.test/api/price/')) {
      return new Response(JSON.stringify({ points: [] }), { status: 200 });
    }
    if (url === 'https://example.test/api/diag') {
      return new Response(JSON.stringify({ plan: diagPlan }), { status: 200 });
    }
    if (url === 'https://example.test/api/version' && version !== undefined) {
      return new Response(JSON.stringify({ version }), { status: 200 });
    }
    throw new Error(`unexpected fetch ${url}`);
  };
}

function buildMarketItem(index, overrides = {}) {
  const rank = index + 1;
  return {
    coin_id: `coin-${rank}`,
    name: `Coin ${rank}`,
    symbol: `c${rank}`,
    logo_url: `https://img.test/coin-${rank}.png`,
    rank,
    price: 1000 - rank,
    market_cap: 1_000_000 - rank * 10,
    fully_diluted_market_cap: 1_500_000 - rank * 20,
    volume_24h: 500_000 - rank * 5,
    pct_change_24h: (rank % 5) - 2,
    pct_change_7d: (rank % 7) - 3,
    pct_change_30d: (rank % 9) - 4,
    category_names: [],
    ...overrides,
  };
}

test('loadCryptos renders table and last update with categories', async (t) => {
  const dom = setupDom();
  t.after(() => {
    dom.window.close();
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  });
  const { loadCryptos, loadVersion } = await import('../frontend/main.js');
  const coins = [
    {
      coin_id: 'bitcoin',
      name: 'Bitcoin',
      symbol: 'btc',
      logo_url: 'https://img.test/bitcoin.png',
      rank: 1,
      price: 1,
      market_cap: 2,
      fully_diluted_market_cap: 3,
      volume_24h: 3,
      pct_change_24h: 4,
      pct_change_7d: 5,
      pct_change_30d: 6,
      category_names: ['Layer 1', 'DeFi', 'NFT', 'Payments'],
    },
    {
      coin_id: 'nocat',
      name: '',
      symbol: 'nct',
      logo_url: null,
      rank: 2,
      price: 0.5,
      market_cap: 1,
      fully_diluted_market_cap: 1.5,
      volume_24h: 1,
      pct_change_24h: -2,
      pct_change_7d: -3.25,
      pct_change_30d: -10,
      category_names: [],
    },
    {
      coin_id: 'flat',
      name: 'Flat Coin',
      symbol: 'flt',
      logo_url: 'https://img.test/flat.png',
      rank: 3,
      price: 2,
      market_cap: 2,
      fully_diluted_market_cap: null,
      volume_24h: 0,
      pct_change_24h: 0,
      pct_change_7d: null,
      pct_change_30d: 0,
      category_names: ['Utility'],
    },
  ];
  const lastRefreshAt = '2024-02-20T10:00:00Z';
  global.fetch = mockApiFetch(coins, {
    diagPlan: 'demo',
    version: '1.0.0',
    lastRefreshAt,
    dataSource: 'CoinGecko API',
  });
  await loadVersion();
  await loadCryptos();
  const table = document.getElementById('cryptos');
  assert.equal(table.style.display, 'table');
  const rows = [...document.querySelectorAll('#cryptos tbody tr')];
  assert.equal(rows.length, 3);
  const normalizeCells = (row) =>
    [...row.querySelectorAll('td')].map((cell) => cell.textContent.trim().replace(/\s+/g, ' '));
  const cells1 = normalizeCells(rows[0]);
  assert.deepEqual(cells1, [
    'Bitcoin',
    'Layer 1 DeFi NFT +1',
    '1',
    '1 $',
    '2 $',
    '3 $',
    '3 $',
    '4.00%',
    '5.00%',
    '6.00%',
    'Détails',
  ]);
  const firstLogo = rows[0].querySelector('td img');
  assert.ok(firstLogo);
  assert.equal(firstLogo.getAttribute('src'), 'https://img.test/bitcoin.png');
  assert.equal(firstLogo.getAttribute('alt'), 'Bitcoin');
  const badges = rows[0].querySelectorAll('.badge');
  assert.equal(badges.length, 4);
  assert.equal(badges[0].getAttribute('title'), 'Layer 1');
  assert.equal(badges[3].getAttribute('title'), 'Payments');
  const changeCellsRow1 = rows[0].querySelectorAll('.change-cell');
  assert.equal(changeCellsRow1.length, 3);
  changeCellsRow1.forEach((cell) => {
    assert.equal(cell.classList.contains('change-positive'), true);
    assert.equal(cell.classList.contains('change-negative'), false);
  });
  const cells2 = normalizeCells(rows[1]);
  assert.deepEqual(cells2, [
    'Nocat',
    '',
    '2',
    '0.5 $',
    '1 $',
    '1.5 $',
    '1 $',
    '-2.00%',
    '-3.25%',
    '-10.00%',
    'Détails',
  ]);
  assert.equal(rows[1].querySelector('td img'), null);
  const changeCellsRow2 = rows[1].querySelectorAll('.change-cell');
  assert.equal(changeCellsRow2.length, 3);
  changeCellsRow2.forEach((cell) => {
    assert.equal(cell.classList.contains('change-positive'), false);
    assert.equal(cell.classList.contains('change-negative'), true);
  });
  const cells3 = normalizeCells(rows[2]);
  assert.deepEqual(cells3, [
    'Flat Coin',
    'Utility',
    '3',
    '2 $',
    '2 $',
    '—',
    '0 $',
    '0.00%',
    '',
    '0.00%',
    'Détails',
  ]);
  const changeCellsRow3 = rows[2].querySelectorAll('.change-cell');
  assert.equal(changeCellsRow3.length, 3);
  changeCellsRow3.forEach((cell) => {
    assert.equal(cell.classList.contains('change-positive'), false);
    assert.equal(cell.classList.contains('change-negative'), false);
  });
  const firstLink = rows[0].querySelector('.details-link');
  assert.ok(firstLink);
  assert.equal(firstLink.getAttribute('href'), './coin.html?coin_id=bitcoin');
  assert.equal(
    firstLink.getAttribute('aria-label'),
    'Voir les détails pour Bitcoin'
  );
  assert.equal(document.getElementById('demo-banner').style.display, 'block');
  const lastUpdateText = document.getElementById('last-update').textContent;
  assert.equal(
    lastUpdateText,
    `Dernière mise à jour : ${lastRefreshAt} (source: CoinGecko API)`,
  );
  assert.equal(document.getElementById('summary-market-cap').textContent, '5 $');
  assert.equal(document.getElementById('summary-market-cap-change-24h').textContent, '1.20%');
  assert.equal(
    document
      .getElementById('summary-market-cap-change-24h')
      .classList.contains('change-positive'),
    true,
  );
  assert.equal(document.getElementById('summary-market-cap-change-7d').textContent, '2.25%');
  assert.equal(
    document
      .getElementById('summary-market-cap-change-7d')
      .classList.contains('change-positive'),
    true,
  );
  assert.equal(document.getElementById('summary-volume').textContent, '4 $');
  assert.equal(document.getElementById('summary-volume-change-24h').textContent, '2.50%');
  assert.equal(
    document
      .getElementById('summary-volume-change-24h')
      .classList.contains('change-positive'),
    true,
  );
  assert.equal(document.getElementById('summary-volume-change-7d').textContent, '2.94%');
  assert.equal(
    document
      .getElementById('summary-volume-change-7d')
      .classList.contains('change-positive'),
    true,
  );
  const rankHeader = document.querySelectorAll('#cryptos thead th')[2];
  assert.equal(rankHeader.classList.contains('sort-asc'), true);
  const paginationInfo = document.querySelector('[data-role="pagination-info"]');
  assert.equal(paginationInfo.textContent.trim(), 'Afficher les résultats de 1 à 3 sur 3');
  const pageButtons = document.querySelectorAll('[data-role="pagination-pages"] button');
  assert.equal(pageButtons.length, 1);
  assert.equal(pageButtons[0].dataset.page, '1');
  assert.equal(pageButtons[0].disabled, true);
  assert.equal(document.getElementById('status').textContent.trim(), '');
});

test('loadCryptos paginates large result sets and navigates across pages', async (t) => {
  const dom = setupDom();
  t.after(() => {
    dom.window.close();
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  });
  const { loadCryptos } = await import('../frontend/main.js');
  const coins = Array.from({ length: 55 }, (_, index) => buildMarketItem(index));
  global.fetch = mockApiFetch(coins, { diagPlan: 'pro' });
  await loadCryptos();

  const getNames = () =>
    [...document.querySelectorAll('#cryptos tbody tr')].map((row) =>
      row.querySelectorAll('td')[0].textContent.trim(),
    );
  let names = getNames();
  assert.equal(names.length, 20);
  assert.equal(names[0], 'Coin 1');
  assert.equal(names[19], 'Coin 20');

  const info = document.querySelector('[data-role="pagination-info"]');
  assert.equal(info.textContent.trim(), 'Afficher les résultats de 1 à 20 sur 55');
  const prev = document.querySelector('[data-role="pagination-prev"]');
  const next = document.querySelector('[data-role="pagination-next"]');
  assert.equal(prev.disabled, true);
  assert.equal(next.disabled, false);

  const getPageButtons = () =>
    [...document.querySelectorAll('[data-role="pagination-pages"] button')];
  let pageButtons = getPageButtons();
  assert.deepEqual(
    pageButtons.map((button) => button.dataset.page),
    ['1', '2', '3'],
  );
  assert.equal(pageButtons[0].disabled, true);
  assert.equal(pageButtons[1].disabled, false);
  assert.equal(pageButtons[2].disabled, false);

  next.dispatchEvent(new window.Event('click', { bubbles: true }));
  names = getNames();
  assert.equal(names.length, 20);
  assert.equal(names[0], 'Coin 21');
  assert.equal(names[19], 'Coin 40');
  assert.equal(info.textContent.trim(), 'Afficher les résultats de 21 à 40 sur 55');
  assert.equal(prev.disabled, false);
  assert.equal(next.disabled, false);
  pageButtons = getPageButtons();
  assert.equal(pageButtons[1].disabled, true);

  const pageThree = pageButtons.find((button) => button.dataset.page === '3');
  assert.ok(pageThree);
  pageThree.dispatchEvent(new window.Event('click', { bubbles: true }));
  names = getNames();
  assert.equal(names.length, 15);
  assert.equal(names[0], 'Coin 41');
  assert.equal(names[names.length - 1], 'Coin 55');
  assert.equal(info.textContent.trim(), 'Afficher les résultats de 41 à 55 sur 55');
  assert.equal(prev.disabled, false);
  assert.equal(next.disabled, true);
  pageButtons = getPageButtons();
  assert.equal(pageButtons[2].disabled, true);
});

test('loadCryptos hides demo banner when plan is not demo', async (t) => {
  const dom = setupDom();
  t.after(() => {
    dom.window.close();
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  });
  const { loadCryptos } = await import('../frontend/main.js');
  global.fetch = mockApiFetch([], { diagPlan: 'pro' });
  await loadCryptos();
  assert.equal(document.getElementById('demo-banner').style.display, 'none');
});

test('loadCryptos handles failure', async (t) => {
  const dom = setupDom();
  t.after(() => {
    dom.window.close();
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  });
  const { loadCryptos } = await import('../frontend/main.js');
  global.fetch = mockApiFetch([], { diagPlan: 'pro', failMarkets: true });
  await loadCryptos();

  const statusEl = document.getElementById('status');
  assert.match(statusEl.innerHTML, /Erreur lors de la récupération des données/);
  const retry = document.getElementById('retry');
  assert.ok(retry);
  assert.equal(typeof retry.onclick, 'function');
  assert.equal(retry.textContent.trim(), 'Réessayer');
  assert.equal(retry.onclick, loadCryptos);

  const table = document.getElementById('cryptos');
  assert.equal(table.style.display, 'none');
  const pagination = document.getElementById('market-pagination');
  assert.equal(pagination.hidden, true);
  const info = document.querySelector('[data-role="pagination-info"]');
  assert.equal(info.textContent.trim(), 'Aucun résultat');
});

test('clicking rank header toggles ascending then descending order', async (t) => {
  const dom = setupDom();
  t.after(() => {
    dom.window.close();
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  });
  const { loadCryptos } = await import('../frontend/main.js');
  const coins = [
    {
      coin_id: 'beta',
      name: 'Beta',
      rank: 2,
      price: 10,
      market_cap: 3,
      fully_diluted_market_cap: 4,
      volume_24h: 5,
      pct_change_24h: -1,
      pct_change_7d: -2,
      pct_change_30d: -3,
    },
    {
      coin_id: 'delta',
      name: 'Delta',
      rank: 4,
      price: 20,
      market_cap: 2,
      fully_diluted_market_cap: 3,
      volume_24h: 4,
      pct_change_24h: 6,
      pct_change_7d: 7,
      pct_change_30d: 8,
    },
    {
      coin_id: 'alpha',
      name: 'Alpha',
      rank: 1,
      price: 30,
      market_cap: 1,
      fully_diluted_market_cap: 2,
      volume_24h: 3,
      pct_change_24h: 9,
      pct_change_7d: 10,
      pct_change_30d: 11,
    },
  ];
  global.fetch = mockApiFetch(coins, { diagPlan: 'pro' });
  await loadCryptos();

  const ranks = () =>
    [...document.querySelectorAll('#cryptos tbody tr')].map((row) =>
      Number(row.querySelectorAll('td')[2].textContent)
    );
  assert.deepEqual(ranks(), [1, 2, 4]);

  const rankHeader = document.querySelectorAll('#cryptos thead th')[2];
  assert.equal(rankHeader.classList.contains('sort-asc'), true);
  rankHeader.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.deepEqual(ranks(), [4, 2, 1]);
  assert.equal(rankHeader.classList.contains('sort-desc'), true);

  rankHeader.dispatchEvent(new window.Event('click', { bubbles: true }));
  assert.deepEqual(ranks(), [1, 2, 4]);
  assert.equal(rankHeader.classList.contains('sort-asc'), true);
});

test('sorting numeric columns keeps null values at the end', async (t) => {
  const dom = setupDom();
  t.after(() => {
    dom.window.close();
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  });
  const { loadCryptos } = await import('../frontend/main.js');
  const coins = [
    {
      coin_id: 'null-price',
      name: 'Null price',
      rank: 1,
      price: null,
      market_cap: 3,
      fully_diluted_market_cap: 5,
      volume_24h: 7,
      pct_change_24h: null,
      pct_change_7d: 2,
      pct_change_30d: 3,
    },
    {
      coin_id: 'negative',
      name: '',
      rank: 2,
      price: -3,
      market_cap: 2,
      fully_diluted_market_cap: null,
      volume_24h: 5,
      pct_change_24h: -5,
      pct_change_7d: -1,
      pct_change_30d: -2,
    },
    {
      coin_id: 'positive',
      name: 'Positive',
      rank: 3,
      price: 15,
      market_cap: 1,
      fully_diluted_market_cap: 2,
      volume_24h: null,
      pct_change_24h: 4,
      pct_change_7d: 6,
      pct_change_30d: 8,
    },
  ];
  global.fetch = mockApiFetch(coins, { diagPlan: 'pro' });
  await loadCryptos();

  const priceHeader = document.querySelectorAll('#cryptos thead th')[3];
  priceHeader.dispatchEvent(new window.Event('click', { bubbles: true }));
  let order = [...document.querySelectorAll('#cryptos tbody tr')].map((row) =>
    row.querySelectorAll('td')[0].textContent.trim()
  );
  assert.deepEqual(order, ['Negative', 'Positive', 'Null price']);

  priceHeader.dispatchEvent(new window.Event('click', { bubbles: true }));
  order = [...document.querySelectorAll('#cryptos tbody tr')].map((row) =>
    row.querySelectorAll('td')[0].textContent.trim()
  );
  assert.deepEqual(order, ['Positive', 'Negative', 'Null price']);
});

test('selectedCategories defaults to empty array', async () => {
  const { selectedCategories } = await import('../frontend/main.js');
  assert.deepEqual(selectedCategories, []);
});

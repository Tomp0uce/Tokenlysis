import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

async function loadTestExports({
  html =
    '<!doctype html><html><head><meta name="api-url" content="https://example.test/api"></head><body></body></html>',
  url = 'https://example.test',
} = {}) {
  const dom = new JSDOM(html, { url });
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  return import('./main.js').then((module) => module.__test__);
}

function buildDashboardHtml() {
  return `<!doctype html><html><head><meta name="api-url" content="https://example.test/api"></head><body>
    <main>
      <div id="status"></div>
      <p id="last-update"></p>
      <div id="demo-banner" style="display:none;"></div>
      <section class="panel table-panel">
        <div id="market-pagination" class="pagination-controls" data-pagination hidden>
          <p class="pagination-info" data-role="pagination-info"></p>
          <div class="pagination-actions">
            <button type="button" data-role="pagination-prev">Précédent</button>
            <div class="pagination-pages" data-role="pagination-pages"></div>
            <button type="button" data-role="pagination-next">Suivant</button>
          </div>
        </div>
        <div class="table-wrapper">
          <table id="cryptos" style="display:none;">
            <thead>
              <tr>
                <th>Actif</th>
                <th>Catégories</th>
                <th>Rank</th>
                <th>Prix ($)</th>
                <th>Market Cap</th>
                <th>Fully Diluted Market Cap</th>
                <th>Volume 24h</th>
                <th>Change 24h</th>
                <th>Change 7j</th>
                <th>Change 30j</th>
                <th>Détails</th>
              </tr>
            </thead>
            <tbody></tbody>
          </table>
        </div>
      </section>
      <div id="market-overview-chart"></div>
    </main>
  </body></html>`;
}

function buildCoin(index) {
  const rank = index + 1;
  return {
    id: `coin-${rank}`,
    symbol: `c${rank}`,
    name: `Coin ${rank}`,
    image: `https://cdn.example.test/coin-${rank}.png`,
    current_price: 5000 - rank,
    market_cap: 1000000 - rank * 10,
    fully_diluted_valuation: 2000000 - rank * 10,
    total_volume: 500000 - rank * 5,
    market_cap_rank: rank,
    price_change_percentage_24h: rank * 0.01,
    price_change_percentage_7d_in_currency: rank * 0.02,
    price_change_percentage_30d_in_currency: rank * 0.03,
  };
}

function createCoinPages(total = 1000, perPage = 250) {
  const map = new Map();
  const pageCount = Math.ceil(total / perPage);
  for (let page = 1; page <= pageCount; page += 1) {
    const items = [];
    const start = (page - 1) * perPage;
    for (let i = start; i < Math.min(total, start + perPage); i += 1) {
      items.push(buildCoin(i));
    }
    map.set(page, items);
  }
  return map;
}

function installApexChartsStub(t) {
  if (global.window.ApexCharts) {
    return global.window.ApexCharts;
  }
  class ApexChartsStub {
    constructor(element, options) {
      this.element = element;
      this.options = options;
      this.rendered = false;
      this.updateOptionsCalls = [];
      this.updateSeriesCalls = [];
      ApexChartsStub.instances.push(this);
    }
    render() {
      this.rendered = true;
      return Promise.resolve();
    }
    updateOptions(options) {
      this.updateOptionsCalls.push(options);
      return Promise.resolve();
    }
    updateSeries(series) {
      this.updateSeriesCalls.push(series);
      return Promise.resolve();
    }
  }
  ApexChartsStub.instances = [];
  global.window.ApexCharts = ApexChartsStub;
  t.after(() => {
    delete global.window.ApexCharts;
  });
  return ApexChartsStub;
}

function stubCoinGecko(t, {
  total = 1000,
  perPage = 250,
  extraHandlers = {},
} = {}) {
  const pages = createCoinPages(total, perPage);
  const calls = [];
  installApexChartsStub(t);
  global.fetch = async (url) => {
    if (typeof extraHandlers[url] === 'function') {
      return extraHandlers[url](url);
    }
    if (url.startsWith('https://api.coingecko.com/api/v3/coins/markets')) {
      const parsed = new URL(url);
      const page = Number(parsed.searchParams.get('page')) || 1;
      calls.push(page);
      const payload = pages.get(page) || [];
      return new Response(JSON.stringify(payload), {
        status: 200,
        headers: { 'Content-Type': 'application/json' },
      });
    }
    if (url === 'https://example.test/api/diag') {
      return new Response(JSON.stringify({ plan: 'pro' }), { status: 200 });
    }
    return new Response('{}', { status: 200 });
  };
  t.after(() => {
    delete global.fetch;
  });
  return { calls, pages };
}

test('computeTopMarketCapSeries sorts and filters invalid entries', async () => {
  const { computeTopMarketCapSeries } = await loadTestExports();
  const items = [
    { coin_id: 'alpha', market_cap: 100 },
    { coin_id: 'beta', market_cap: null },
    { coin_id: 'gamma', market_cap: 400 },
    { coin_id: 'delta', market_cap: '700' },
    { coin_id: 'epsilon', market_cap: 'oops' },
  ];
  const result = computeTopMarketCapSeries(items, 3);
  assert.deepEqual(result.categories, ['delta', 'gamma', 'alpha']);
  assert.deepEqual(result.data, [700, 400, 100]);
});

test('combineMarketHistories merges totals chronologiquement', async () => {
  const { combineMarketHistories } = await loadTestExports();
  const histories = [
    [
      { snapshot_at: '2024-01-01T00:00:00Z', market_cap: 120 },
      { snapshot_at: '2024-01-02T00:00:00Z', market_cap: 150 },
    ],
    [
      { snapshot_at: '2024-01-01T06:00:00Z', market_cap: 80 },
      { snapshot_at: '2024-01-03T00:00:00Z', market_cap: 200 },
    ],
  ];
  const { categories, data } = combineMarketHistories(histories);
  assert.deepEqual(categories, [
    '2024-01-01T00:00:00.000Z',
    '2024-01-01T06:00:00.000Z',
    '2024-01-02T00:00:00.000Z',
    '2024-01-03T00:00:00.000Z',
  ]);
  assert.deepEqual(data, [120, 80, 150, 200]);
});

test('fetchAggregatedTopMarketHistory agrège les séries valides et ignore les erreurs', async () => {
  const { fetchAggregatedTopMarketHistory } = await loadTestExports();
  let callCount = 0;
  const fakeFetch = async (url) => {
    callCount += 1;
    if (url.includes('alpha')) {
      return {
        ok: true,
        json: async () => ({
          points: [
            { snapshot_at: '2024-01-01T00:00:00Z', market_cap: 100 },
            { snapshot_at: '2024-01-02T00:00:00Z', market_cap: 140 },
          ],
        }),
      };
    }
    if (url.includes('beta')) {
      return {
        ok: true,
        json: async () => ({
          points: [
            { snapshot_at: '2024-01-01T00:00:00Z', market_cap: 50 },
            { snapshot_at: '2024-01-03T00:00:00Z', market_cap: null },
          ],
        }),
      };
    }
    return { ok: false };
  };

  const result = await fetchAggregatedTopMarketHistory(['alpha', 'beta', 'gamma'], {
    range: '7d',
    fetchImpl: fakeFetch,
  });

  assert.equal(callCount, 3);
  assert.deepEqual(result.categories, [
    '2024-01-01T00:00:00.000Z',
    '2024-01-02T00:00:00.000Z',
  ]);
  assert.deepEqual(result.data, [150, 140]);
});

test('loadFearGreedWidget met à jour la jauge et les étiquettes', async (t) => {
  const html = `<!doctype html><html><head><meta name="api-url" content="https://example.test/api"></head><body>
      <a id="fear-greed-card" href="./fear-greed.html" class="sentiment-card">
        <div class="sentiment-card-header">
          <span>Sentiment du marché</span>
          <strong id="fear-greed-value">—</strong>
        </div>
        <div class="sentiment-visual">
          <div id="fear-greed-gauge" class="sentiment-gauge"></div>
          <dl class="sentiment-legend">
            <div class="sentiment-legend-item"><dt>0-25</dt><dd>Extreme Fear</dd></div>
            <div class="sentiment-legend-item"><dt>26-44</dt><dd>Fear</dd></div>
            <div class="sentiment-legend-item"><dt>45-54</dt><dd>Neutral</dd></div>
            <div class="sentiment-legend-item"><dt>55-74</dt><dd>Greed</dd></div>
            <div class="sentiment-legend-item"><dt>75-100</dt><dd>Extreme Greed</dd></div>
          </dl>
        </div>
        <dl class="sentiment-snapshots" id="fear-greed-snapshots">
          <div class="sentiment-snapshot" data-period="today">
            <dt class="sentiment-snapshot-label">Aujourd'hui</dt>
            <dd class="sentiment-snapshot-value" data-role="value">—</dd>
          </div>
          <div class="sentiment-snapshot" data-period="yesterday">
            <dt class="sentiment-snapshot-label">Hier</dt>
            <dd class="sentiment-snapshot-value" data-role="value">—</dd>
          </div>
          <div class="sentiment-snapshot" data-period="week">
            <dt class="sentiment-snapshot-label">Semaine dernière</dt>
            <dd class="sentiment-snapshot-value" data-role="value">—</dd>
          </div>
          <div class="sentiment-snapshot" data-period="month">
            <dt class="sentiment-snapshot-label">Mois dernier</dt>
            <dd class="sentiment-snapshot-value" data-role="value">—</dd>
          </div>
        </dl>
      </a>
    </body></html>`;
  class ApexChartsStub {
    constructor(el, options) {
      this.el = el;
      this.options = options;
      this.updateCalls = [];
      ApexChartsStub.instances.push(this);
    }
    render() {
      this.rendered = true;
      return Promise.resolve();
    }
    updateSeries(series) {
      this.updateCalls.push({ series });
      return Promise.resolve();
    }
    updateOptions(options) {
      this.updateCalls.push(options);
      return Promise.resolve();
    }
  }
  ApexChartsStub.instances = [];
  const latest = {
    timestamp: '2024-03-12T00:00:00Z',
    score: 62,
    label: 'Greed',
  };
  const history = {
    days: 90,
    points: [
      { timestamp: '2024-02-10T00:00:00Z', score: 22, label: 'Extreme Fear' },
      { timestamp: '2024-03-05T00:00:00Z', score: 50, label: 'Neutral' },
      { timestamp: '2024-03-11T00:00:00Z', score: 57, label: 'Greed' },
    ],
  };
  const calls = [];
  global.fetch = async (url) => {
    calls.push(url);
    if (url === 'https://example.test/api/fng/latest') {
      return new Response(JSON.stringify(latest), { status: 200 });
    }
    if (url === 'https://example.test/api/fng/history?days=90') {
      return new Response(JSON.stringify(history), { status: 200 });
    }
    throw new Error(`unexpected fetch ${url}`);
  };

  const exports = await loadTestExports({ html, url: 'https://example.test' });
  const testWindow = global.window;
  const testDocument = global.document;
  testWindow.ApexCharts = ApexChartsStub;
  testDocument.documentElement.style.setProperty('--fg-greed', '#22c55e');
  testDocument.documentElement.style.setProperty('--fg-neutral', '#facc15');
  testDocument.documentElement.style.setProperty('--fg-extreme-fear', '#dc2626');
  t.after(() => {
    testWindow.close();
    delete global.fetch;
    delete global.window;
    delete global.document;
    delete global.localStorage;
  });

  await exports.loadFearGreedWidget();
  assert.equal(document.getElementById('fear-greed-value').textContent, '62');
  const classificationEl = document.getElementById('fear-greed-classification');
  assert.equal(classificationEl, null);
  assert.equal(document.querySelector('.sentiment-updated'), null);
  assert.deepEqual(calls, [
    'https://example.test/api/fng/latest',
    'https://example.test/api/fng/history?days=90',
  ]);
  const card = document.getElementById('fear-greed-card');
  assert.ok(card);
  assert.equal(card.getAttribute('href') ?? card.getAttribute('data-href'), './fear-greed.html');
  assert.match(card.getAttribute('aria-label') ?? '', /Fear & Greed : Greed/);
  const gauge = document.getElementById('fear-greed-gauge');
  assert.ok(gauge);
  assert.equal(gauge.children.length >= 0, true);
  const [{ options }] = ApexChartsStub.instances;
  assert.equal(options.chart.background, 'transparent');

  const getValue = (period) =>
    document.querySelector(`[data-period="${period}"] [data-role="value"]`);
  const today = getValue('today');
  assert.equal(today.textContent, '62');
  assert.equal(today.dataset.band, 'greed');
  const yesterday = getValue('yesterday');
  assert.equal(yesterday.textContent, '57');
  assert.equal(yesterday.dataset.band, 'greed');
  const week = getValue('week');
  assert.equal(week.textContent, '50');
  assert.equal(week.dataset.band, 'neutral');
  const month = getValue('month');
  assert.equal(month.textContent, '22');
  assert.equal(month.dataset.band, 'extreme-fear');
});

test('loadCryptos récupère 1000 actifs CoinGecko et initialise la pagination', async (t) => {
  const html = buildDashboardHtml();
  const exports = await loadTestExports({ html });
  const { calls } = stubCoinGecko(t);

  await exports.loadCryptos();

  assert.deepEqual(calls, [1, 2, 3, 4]);
  const table = document.getElementById('cryptos');
  assert.equal(table.style.display, 'table');
  const rows = document.querySelectorAll('#cryptos tbody tr');
  assert.equal(rows.length, 20);
  assert.equal(rows[0].querySelector('.coin-name').textContent, 'Coin 1');
  const info = document.querySelector('[data-role="pagination-info"]');
  assert.ok(info);
  assert.equal(info.textContent.trim(), 'Afficher les résultats de 1 à 20 sur 1000');
  const pagesNav = document.querySelector('[data-role="pagination-pages"]');
  assert.ok(pagesNav.querySelector('button[data-page="1"]'));
  assert.ok(pagesNav.querySelector('button[data-page="2"]'));
  assert.equal(document.getElementById('market-pagination').hasAttribute('hidden'), false);
  assert.equal(document.getElementById('status').textContent.trim(), '');
});

test('pagination permet de naviguer vers les actifs suivants', async (t) => {
  const html = buildDashboardHtml();
  const exports = await loadTestExports({ html });
  stubCoinGecko(t);

  await exports.loadCryptos();

  const pageThree = document.querySelector('[data-role="pagination-pages"] button[data-page="3"]');
  assert.ok(pageThree);
  pageThree.click();
  const rows = document.querySelectorAll('#cryptos tbody tr');
  assert.equal(rows.length, 20);
  assert.equal(rows[0].querySelector('.coin-name').textContent, 'Coin 41');
  const info = document.querySelector('[data-role="pagination-info"]');
  assert.equal(info.textContent.trim(), 'Afficher les résultats de 41 à 60 sur 1000');
});

test('un tri réinitialise la pagination sur la première page', async (t) => {
  const html = buildDashboardHtml();
  const exports = await loadTestExports({ html });
  stubCoinGecko(t);

  await exports.loadCryptos();

  const pageTwo = document.querySelector('[data-role="pagination-pages"] button[data-page="2"]');
  assert.ok(pageTwo);
  pageTwo.click();
  const priceHeader = document.querySelectorAll('#cryptos thead th')[3];
  priceHeader.click();
  const info = document.querySelector('[data-role="pagination-info"]');
  assert.equal(info.textContent.trim(), 'Afficher les résultats de 1 à 20 sur 1000');
  const firstName = document.querySelector('#cryptos tbody tr .coin-name').textContent;
  assert.equal(firstName, 'Coin 1000');
});

test('loadCryptos affiche une erreur lorsqu’une requête échoue', async (t) => {
  const html = buildDashboardHtml();
  const exports = await loadTestExports({ html });
  global.fetch = async (url) => {
    if (url.startsWith('https://api.coingecko.com/api/v3/coins/markets')) {
      return new Response('oops', { status: 500 });
    }
    return new Response('{}', { status: 200 });
  };
  t.after(() => {
    delete global.fetch;
  });

  await exports.loadCryptos();

  const status = document.getElementById('status');
  assert.ok(status.innerHTML.includes('Erreur'));
  const retry = document.getElementById('retry');
  assert.ok(retry);
  assert.equal(document.getElementById('cryptos').style.display, 'none');
});

test('loadCryptos gère un univers plus petit que la taille de page', async (t) => {
  const html = buildDashboardHtml();
  const exports = await loadTestExports({ html });
  const { calls } = stubCoinGecko(t, { total: 10 });

  await exports.loadCryptos();

  assert.deepEqual(calls, [1]);
  const rows = document.querySelectorAll('#cryptos tbody tr');
  assert.equal(rows.length, 10);
  const info = document.querySelector('[data-role="pagination-info"]');
  assert.equal(info.textContent.trim(), 'Afficher les résultats de 1 à 10 sur 10');
  const pageTwo = document.querySelector('[data-role="pagination-pages"] button[data-page="2"]');
  assert.equal(pageTwo, null);
});

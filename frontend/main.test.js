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
        <p id="fear-greed-classification">—</p>
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
  assert.equal(document.getElementById('fear-greed-classification').textContent, 'Greed');
  assert.equal(document.querySelector('.sentiment-updated'), null);
  assert.deepEqual(calls, [
    'https://example.test/api/fng/latest',
    'https://example.test/api/fng/history?days=90',
  ]);
  const card = document.getElementById('fear-greed-card');
  assert.ok(card);
  assert.equal(card.getAttribute('href') ?? card.getAttribute('data-href'), './fear-greed.html');
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

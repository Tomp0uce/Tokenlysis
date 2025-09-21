import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

let testExportsPromise;

async function loadTestExports() {
  if (!testExportsPromise) {
    const initialDom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
    global.window = initialDom.window;
    global.document = initialDom.window.document;
    global.localStorage = initialDom.window.localStorage;
    testExportsPromise = import('./coin.js').then((module) => module.__test__);
  }
  return testExportsPromise;
}

function setupCoinDom() {
  const dom = new JSDOM(
    `<!doctype html><html><head><title>Tokenlysis – Détails</title></head><body>
      <main>
        <h1 id="coin-title" class="coin-title">
          <img id="coin-logo" class="coin-logo" alt="" hidden>
          <span id="coin-title-text">Détails</span>
        </h1>
        <strong id="price-value">—</strong>
        <small id="price-updated">—</small>
        <strong id="market-cap-value">—</strong>
        <strong id="volume-value">—</strong>
        <div id="categories"></div>
      </main>
    </body></html>`,
    { url: 'http://localhost' },
  );
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  return dom;
}

test('buildHistoricalDataset keeps a shared timeline and nulls invalid values', async () => {
  const { buildHistoricalDataset } = await loadTestExports();
  const points = [
    { snapshot_at: '2024-01-01T00:00:00Z', price: 10, market_cap: 1000, volume_24h: 500 },
    { snapshot_at: '2024-01-02T00:00:00Z', price: 'not-a-number', market_cap: '2000', volume_24h: null },
    { snapshot_at: '2024-01-03T00:00:00Z', price: 12.5, market_cap: undefined, volume_24h: '300' },
  ];

  const dataset = buildHistoricalDataset(points);

  assert.deepEqual(dataset.categories, [
    '2024-01-01T00:00:00Z',
    '2024-01-02T00:00:00Z',
    '2024-01-03T00:00:00Z',
  ]);
  assert.deepEqual(dataset.price, [10, null, 12.5]);
  assert.deepEqual(dataset.marketCap, [1000, 2000, null]);
  assert.deepEqual(dataset.volume, [500, null, 300]);
});

test('buildHistoricalDataset returns empty arrays when no valid points exist', async () => {
  const { buildHistoricalDataset } = await loadTestExports();
  const dataset = buildHistoricalDataset([]);
  assert.deepEqual(dataset.categories, []);
  assert.deepEqual(dataset.price, []);
  assert.deepEqual(dataset.marketCap, []);
  assert.deepEqual(dataset.volume, []);
});

test('formatUsd abbreviates large values using k$, M$, B$ and T$', async () => {
  const { formatUsd } = await loadTestExports();

  assert.equal(formatUsd(999), '999 $');
  assert.equal(formatUsd(1500), '1.5 k$');
  assert.equal(formatUsd(2_345_000), '2.35 M$');
  assert.equal(formatUsd(3_456_000_000), '3.46 B$');
  assert.equal(formatUsd(7_890_000_000_000), '7.89 T$');
  assert.equal(formatUsd(-12_300_000), '-12.3 M$');
});

test('renderDetail updates title, metrics and logo with compact values', async () => {
  const { renderDetail } = await loadTestExports();
  const dom = setupCoinDom();

  renderDetail({
    coin_id: 'bitcoin',
    price: 115_561,
    market_cap: 2_300_000_000_000,
    volume_24h: 19_000_000_000,
    snapshot_at: '2024-01-31T12:30:00Z',
    category_names: ['Layer 1', 'Payments'],
    logo_url: 'https://img.test/bitcoin.png',
  });

  const titleText = dom.window.document.getElementById('coin-title-text').textContent.trim();
  assert.equal(titleText, 'Bitcoin');
  assert.equal(dom.window.document.title, 'Tokenlysis – Bitcoin');

  const marketCapText = dom.window.document.getElementById('market-cap-value').textContent;
  const volumeText = dom.window.document.getElementById('volume-value').textContent;
  assert.equal(marketCapText, '2.3 T$');
  assert.equal(volumeText, '19 B$');

  const logo = dom.window.document.getElementById('coin-logo');
  assert.equal(logo.getAttribute('src'), 'https://img.test/bitcoin.png');
  assert.equal(logo.getAttribute('alt'), 'Bitcoin');
  assert.equal(logo.hasAttribute('hidden'), false);
});

test('renderDetail hides the logo when url is missing and falls back to coin id', async () => {
  const { renderDetail } = await loadTestExports();
  const dom = setupCoinDom();

  renderDetail({
    coin_id: 'my-coin',
    price: 1,
    market_cap: 800,
    volume_24h: null,
    snapshot_at: '2024-02-01T00:00:00Z',
    category_names: [],
    logo_url: '',
  });

  const titleText = dom.window.document.getElementById('coin-title-text').textContent.trim();
  assert.equal(titleText, 'My Coin');

  const logo = dom.window.document.getElementById('coin-logo');
  assert.equal(logo.getAttribute('src'), '');
  assert.equal(logo.hasAttribute('hidden'), true);
  assert.equal(logo.getAttribute('alt'), '');
  const volumeText = dom.window.document.getElementById('volume-value').textContent;
  assert.equal(volumeText, '—');
});

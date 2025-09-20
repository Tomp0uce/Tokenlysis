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

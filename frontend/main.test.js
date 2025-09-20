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

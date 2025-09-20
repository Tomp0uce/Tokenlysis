import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

import { RANGE_OPTIONS, calculateAvailableRanges, pickInitialRange, syncRangeSelector } from './range.js';

test('calculateAvailableRanges returns ranges covered by history span', () => {
  const timestamps = [
    '2020-01-01T00:00:00Z',
    '2021-01-01T00:00:00Z',
    '2023-06-01T00:00:00Z',
    '2024-01-01T00:00:00Z',
  ];
  const available = calculateAvailableRanges(timestamps, { now: Date.parse('2024-01-01T00:00:00Z') });
  assert.deepEqual(Array.from(available), ['24h', '7d', '1m', '3m', '1y', '2y', 'max']);
});

test('pickInitialRange keeps preferred range when available and falls back gracefully', () => {
  const available = new Set(['24h', '7d', 'max']);
  assert.equal(pickInitialRange(available, '7d'), '7d');
  assert.equal(pickInitialRange(available, '1m'), '7d');
  assert.equal(pickInitialRange(available, '5y'), 'max');
  assert.equal(pickInitialRange(new Set(), '1m'), null);
});

test('syncRangeSelector hides and disables unavailable options', () => {
  const markup = `<!doctype html><html><body><div id="selector">${RANGE_OPTIONS.map(
    (opt) => `<button data-range="${opt.key}">${opt.label}</button>`,
  ).join('')}</div></body></html>`;
  const { window } = new JSDOM(markup);
  const container = window.document.getElementById('selector');
  const available = new Set(['1m', '5y', 'max']);

  const visibleCount = syncRangeSelector(container, available);

  const buttons = [...container.querySelectorAll('[data-range]')];
  const visibleKeys = buttons.filter((btn) => !btn.hidden).map((btn) => btn.dataset.range);
  const hiddenKeys = buttons.filter((btn) => btn.hidden).map((btn) => btn.dataset.range);

  assert.deepEqual(visibleKeys, ['1m', '5y', 'max']);
  assert.deepEqual(hiddenKeys, ['24h', '7d', '3m', '1y', '2y']);
  assert.equal(visibleCount, 3);

  const disabledHidden = buttons.filter((btn) => btn.hidden && btn.disabled).map((btn) => btn.dataset.range);
  assert.deepEqual(disabledHidden, hiddenKeys);
});

test('calculateAvailableRanges ignores invalid timestamps', () => {
  const timestamps = ['invalid', null, undefined, '2024-01-01T00:00:00Z'];
  const available = calculateAvailableRanges(timestamps, { now: Date.parse('2024-01-02T00:00:00Z') });
  assert.deepEqual(Array.from(available), ['max']);
});

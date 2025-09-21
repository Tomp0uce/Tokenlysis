import assert from 'node:assert/strict';
import test from 'node:test';

import { evaluateRatios } from '../frontend/debug.js';

function closeTo(value, expected, epsilon = 1e-6) {
  assert.ok(Math.abs(value - expected) <= epsilon, `${value} not within ${epsilon} of ${expected}`);
}

test('evaluateRatios returns normalized ratios and statuses', () => {
  const diag = {
    last_etl_items: 20,
    top_n: 20,
    monthly_call_count: 820,
    quota: 1000,
  };

  const metrics = evaluateRatios(diag);

  assert.equal(metrics.etl.status, 'ok');
  closeTo(metrics.etl.ratio, 1);
  assert.equal(metrics.budget.status, 'warn');
  closeTo(metrics.budget.ratio, 0.82);
});

test('evaluateRatios flags abnormal values and handles empty denominators', () => {
  const diag = {
    last_etl_items: 5,
    top_n: 20,
    monthly_call_count: 1200,
    quota: 0,
  };

  const metrics = evaluateRatios(diag);

  assert.equal(metrics.etl.status, 'error');
  closeTo(metrics.etl.ratio, 0.25);
  assert.equal(metrics.budget.status, 'unknown');
  assert.equal(metrics.budget.ratio, null);
});

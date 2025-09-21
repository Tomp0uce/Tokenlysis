import assert from 'node:assert/strict';
import test from 'node:test';

import {
  evaluateRatios,
  evaluateFreshness,
  summarizeCategoryIssues,
  normalizeBudgetCategories,
} from '../frontend/debug.js';

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

test('evaluateFreshness reports ok when lag stays within the configured granularity', () => {
  const now = Date.UTC(2024, 0, 2, 0, 0, 0);
  const lastRefreshAt = new Date(now - 6 * 60 * 60 * 1000).toISOString();

  const metrics = evaluateFreshness({
    lastRefreshAt,
    granularity: '24h',
    stale: false,
    nowMs: now,
  });

  closeTo(metrics.differenceHours, 6);
  assert.equal(metrics.granularityHours, 24);
  closeTo(metrics.ratio, 0.25);
  assert.equal(metrics.status, 'ok');
});

test('evaluateFreshness escalates server-stale signals even when lag is small', () => {
  const now = Date.UTC(2024, 0, 2, 0, 0, 0);
  const lastRefreshAt = new Date(now - 2 * 60 * 60 * 1000).toISOString();

  const metrics = evaluateFreshness({
    lastRefreshAt,
    granularity: '24h',
    stale: true,
    nowMs: now,
  });

  assert.equal(metrics.status, 'error');
  closeTo(metrics.differenceHours, 2);
});

test('evaluateFreshness downgrades to warn when lag exceeds granularity but not by much', () => {
  const now = Date.UTC(2024, 0, 3, 12, 0, 0);
  const lastRefreshAt = new Date(now - 36 * 60 * 60 * 1000).toISOString();

  const metrics = evaluateFreshness({
    lastRefreshAt,
    granularity: '24h',
    stale: false,
    nowMs: now,
  });

  closeTo(metrics.differenceHours, 36);
  closeTo(metrics.granularityHours, 24);
  closeTo(metrics.ratio, 1.5);
  assert.equal(metrics.status, 'warn');
});

test('evaluateFreshness handles invalid timestamps gracefully', () => {
  const metrics = evaluateFreshness({
    lastRefreshAt: 'not-a-date',
    granularity: '24h',
    stale: false,
    nowMs: Date.UTC(2024, 0, 1, 0, 0, 0),
  });

  assert.equal(metrics.differenceHours, null);
  assert.equal(metrics.ratio, null);
  assert.equal(metrics.status, 'unknown');
});

test('summarizeCategoryIssues tallies missing and stale diagnostics', () => {
  const summary = summarizeCategoryIssues([
    { coin_id: 'a', reasons: ['missing_categories'] },
    { coin_id: 'b', reasons: ['stale_timestamp'] },
    { coin_id: 'c', reasons: ['missing_categories', 'stale_timestamp'] },
    { coin_id: 'd', reasons: [] },
  ]);

  assert.equal(summary.total, 4);
  assert.equal(summary.missing, 2);
  assert.equal(summary.stale, 2);
  assert.equal(summary.both, 1);
});

test('normalizeBudgetCategories sorts items and computes ratios', () => {
  const diag = {
    monthly_call_count: 10,
    monthly_call_categories: {
      markets: 6,
      coin_profile: 3,
      misc: 1,
    },
  };

  const breakdown = normalizeBudgetCategories(diag);

  assert.equal(breakdown.total, 10);
  assert.deepEqual(breakdown.categories, [
    { name: 'markets', count: 6, ratio: 0.6 },
    { name: 'coin_profile', count: 3, ratio: 0.3 },
    { name: 'misc', count: 1, ratio: 0.1 },
  ]);
});

test('normalizeBudgetCategories filters invalid inputs gracefully', () => {
  const breakdown = normalizeBudgetCategories({
    monthly_call_count: '12',
    monthly_call_categories: {
      markets: 5,
      stale: -2,
      weird: 'oops',
    },
  });

  assert.equal(breakdown.total, 12);
  assert.deepEqual(breakdown.categories, [
    { name: 'markets', count: 5, ratio: 5 / 12 },
  ]);
});

import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

class ApexChartsStub {
  constructor(el, options) {
    this.el = el;
    this.options = options;
    this.updateCalls = [];
  }

  render() {
    this.rendered = true;
    return Promise.resolve();
  }

  updateOptions(options) {
    this.updateCalls.push(options);
    return Promise.resolve();
  }

  destroy() {
    this.destroyed = true;
    return Promise.resolve();
  }
}

test('createAreaChart builds smooth area config with shared categories', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.ApexCharts = ApexChartsStub;
  document.documentElement.style.setProperty('--chart-primary', '#123456');
  document.documentElement.style.setProperty('--text-muted', '#555555');
  document.documentElement.style.setProperty('--border-subtle', '#dddddd');

  const module = await import('./charting.js');
  const container = document.createElement('div');
  document.body.appendChild(container);

  const chart = await module.createAreaChart(container, {
    name: 'Prix',
    categories: ['2024-01-01T00:00:00Z', '2024-01-02T00:00:00Z'],
    data: [10, 12],
    colorVar: '--chart-primary',
  });

  assert.ok(chart instanceof ApexChartsStub);
  assert.equal(chart.options.chart.type, 'area');
  assert.equal(chart.options.stroke.curve, 'smooth');
  assert.equal(chart.options.xaxis.type, 'datetime');
  assert.deepEqual(chart.options.series, [{ name: 'Prix', data: [10, 12] }]);
  assert.deepEqual(chart.options.xaxis.categories, [
    '2024-01-01T00:00:00Z',
    '2024-01-02T00:00:00Z',
  ]);
  await module.destroyTrackedCharts();
});

test('refreshChartsTheme updates theme mode and palette from CSS variables', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.ApexCharts = ApexChartsStub;
  document.documentElement.style.setProperty('--chart-primary', '#112233');
  document.documentElement.style.setProperty('--text-muted', '#222222');
  document.documentElement.style.setProperty('--border-subtle', '#cccccc');

  const module = await import('./charting.js');
  const container = document.createElement('div');
  document.body.appendChild(container);

  await module.createAreaChart(container, {
    name: 'Market Cap',
    categories: ['2024-01-01T00:00:00Z'],
    data: [1000],
    colorVar: '--chart-primary',
  });

  document.documentElement.style.setProperty('--chart-primary', '#445566');
  await module.refreshChartsTheme('dark');

  const registered = module.__test__.getTrackedCharts();
  assert.equal(registered.length, 1);
  const [{ chart }] = registered;
  assert.deepEqual(chart.updateCalls.at(-1).theme, { mode: 'dark' });
  assert.deepEqual(chart.updateCalls.at(-1).colors, ['#445566']);
  await module.destroyTrackedCharts();
});

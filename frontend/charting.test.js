import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

test('formatCompactUsd remplace les suffixes USD par le symbole dollar', async () => {
  const { formatCompactUsd } = await import('./charting.js');
  assert.equal(formatCompactUsd(1_250_000_000), '1.25 B$');
  assert.equal(formatCompactUsd(12_000_000), '12 M$');
  assert.equal(formatCompactUsd(15_000), '15 k$');
  assert.equal(formatCompactUsd(950), '950 $');
  assert.equal(formatCompactUsd(-1_500), '-1.5 k$');
});

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
  assert.equal(chart.options.chart.zoom?.enabled, false);
  assert.equal(chart.options.chart.selection?.enabled, false);
  assert.equal(chart.options.stroke.curve, 'smooth');
  assert.equal(chart.options.xaxis.type, 'datetime');
  assert.deepEqual(chart.options.series, [{ name: 'Prix', data: [10, 12] }]);
  assert.deepEqual(chart.options.xaxis.categories, [
    '2024-01-01T00:00:00Z',
    '2024-01-02T00:00:00Z',
  ]);
  await module.destroyTrackedCharts();
});

test('createAreaChart applies chart id, group and custom events', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.ApexCharts = ApexChartsStub;
  document.documentElement.style.setProperty('--chart-primary', '#654321');
  document.documentElement.style.setProperty('--text-muted', '#222222');
  document.documentElement.style.setProperty('--border-subtle', '#cccccc');

  const module = await import('./charting.js');
  const container = document.createElement('div');
  document.body.appendChild(container);
  const events = {
    dataPointSelection() {},
  };

  const chart = await module.createAreaChart(container, {
    name: 'Volumes',
    categories: [],
    data: [],
    colorVar: '--chart-primary',
    chartId: 'custom-chart',
    chartGroup: 'history-group',
    events,
  });

  assert.equal(chart.options.chart.id, 'custom-chart');
  assert.equal(chart.options.chart.group, 'history-group');
  assert.equal(chart.options.chart.events.dataPointSelection, events.dataPointSelection);
  await module.destroyTrackedCharts();
});

test('createAreaChart supports fear-greed banding and custom formatters', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.ApexCharts = ApexChartsStub;
  document.documentElement.style.setProperty('--chart-sentiment', '#1d4ed8');
  document.documentElement.style.setProperty('--text-muted', '#4b5563');
  document.documentElement.style.setProperty('--border-subtle', '#e2e8f0');
  document.documentElement.style.setProperty('--fg-extreme-fear', '#ef4444');
  document.documentElement.style.setProperty('--fg-fear', '#f97316');
  document.documentElement.style.setProperty('--fg-neutral', '#facc15');
  document.documentElement.style.setProperty('--fg-greed', '#22c55e');
  document.documentElement.style.setProperty('--fg-extreme-greed', '#0ea5e9');

  const module = await import('./charting.js');
  const container = document.createElement('div');
  document.body.appendChild(container);

  const yFormatter = (value) => `${Math.round(value)} pts`;
  const tooltipFormatter = (value) => `${value.toFixed(1)} pts`;

  const chart = await module.createAreaChart(container, {
    name: 'Indice Fear & Greed',
    categories: ['2024-01-01T00:00:00Z'],
    data: [40],
    colorVar: '--chart-sentiment',
    yFormatter,
    tooltipFormatter,
    banding: 'fear-greed',
  });

  assert.equal(chart.options.yaxis.labels.formatter(42.7), '43 pts');
  assert.equal(chart.options.tooltip.y.formatter(42), '42.0 pts');
  assert.equal(chart.options.yaxis.min, 0);
  assert.equal(chart.options.yaxis.max, 100);
  const annotations = chart.options.annotations?.yaxis ?? [];
  assert.equal(annotations.length, 5);
  assert.deepEqual(
    annotations.map((entry) => entry.fillColor),
    ['#ef4444', '#f97316', '#facc15', '#22c55e', '#0ea5e9'],
  );
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

test('refreshChartsTheme recomputes fear-greed bands with updated CSS variables', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.ApexCharts = ApexChartsStub;
  document.documentElement.style.setProperty('--chart-sentiment', '#1d4ed8');
  document.documentElement.style.setProperty('--text-muted', '#4b5563');
  document.documentElement.style.setProperty('--border-subtle', '#e2e8f0');
  document.documentElement.style.setProperty('--fg-extreme-fear', '#ef4444');
  document.documentElement.style.setProperty('--fg-fear', '#f97316');
  document.documentElement.style.setProperty('--fg-neutral', '#facc15');
  document.documentElement.style.setProperty('--fg-greed', '#22c55e');
  document.documentElement.style.setProperty('--fg-extreme-greed', '#0ea5e9');

  const module = await import('./charting.js');
  const container = document.createElement('div');
  document.body.appendChild(container);

  await module.createAreaChart(container, {
    name: 'Indice Fear & Greed',
    categories: ['2024-01-01T00:00:00Z'],
    data: [40],
    colorVar: '--chart-sentiment',
    banding: 'fear-greed',
    yFormatter: (value) => `${Math.round(value)}`,
  });

  document.documentElement.style.setProperty('--fg-extreme-fear', '#f87171');
  document.documentElement.style.setProperty('--fg-fear', '#fb923c');
  document.documentElement.style.setProperty('--fg-neutral', '#fde68a');
  document.documentElement.style.setProperty('--fg-greed', '#86efac');
  document.documentElement.style.setProperty('--fg-extreme-greed', '#38bdf8');

  await module.refreshChartsTheme('light');

  const [{ chart }] = module.__test__.getTrackedCharts();
  const lastUpdate = chart.updateCalls.at(-1);
  assert.ok(lastUpdate.annotations);
  assert.deepEqual(
    lastUpdate.annotations.yaxis.map((entry) => entry.fillColor),
    ['#f87171', '#fb923c', '#fde68a', '#86efac', '#38bdf8'],
  );
  await module.destroyTrackedCharts();
});

test('createRadialGauge chooses palette band and updates value', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.ApexCharts = ApexChartsStub;
  document.documentElement.style.setProperty('--fg-extreme-fear', '#dc2626');
  document.documentElement.style.setProperty('--fg-neutral', '#facc15');
  document.documentElement.style.setProperty('--fg-greed', '#16a34a');

  const module = await import('./charting.js');
  const container = document.createElement('div');
  document.body.appendChild(container);

  const chart = await module.createRadialGauge(container, {
    value: 12,
    classification: 'Extreme Fear',
  });

  assert.ok(chart instanceof ApexChartsStub);
  assert.equal(chart.options.chart.type, 'radialBar');
  assert.equal(chart.options.chart.background, 'transparent');
  assert.deepEqual(chart.options.series, [12]);
  assert.deepEqual(chart.options.labels, ['Extreme Fear']);
  assert.equal(chart.options.colors[0], '#dc2626');
  const gradient = chart.options.fill?.gradient;
  assert.equal(gradient?.opacityFrom, 1);
  assert.equal(gradient?.opacityTo, 1);
  assert.deepEqual(
    gradient?.colorStops?.map((stop) => ({ color: stop.color, opacity: stop.opacity })),
    [
      { color: '#dc2626', opacity: 1 },
      { color: '#dc2626', opacity: 1 },
    ],
  );

  await module.updateRadialGauge(chart, { value: 65, classification: 'Greed' });
  assert.equal(chart.updateCalls.at(-1).series[0], 65);
  assert.equal(chart.updateCalls.at(-1).labels[0], 'Greed');
  assert.equal(chart.updateCalls.at(-1).colors[0], '#16a34a');

  await module.updateRadialGauge(chart, { value: 50, classification: 'Neutral' });
  assert.equal(chart.updateCalls.at(-1).colors[0], '#facc15');

  await module.destroyTrackedCharts();
});

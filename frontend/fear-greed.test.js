import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

class ApexChartsStub {
  static instances = [];

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

function setupDom() {
  const dom = new JSDOM(
    `<!doctype html><html><head><meta name="api-url" content="https://example.test/api"></head><body>
      <main class="dashboard">
        <header class="dashboard-header">
          <a id="back" href="./index.html" class="breadcrumb-link">← Retour</a>
        </header>
        <section class="sentiment-panel">
          <div class="sentiment-card-header">
            <span>Sentiment actuel</span>
            <strong id="fear-greed-value">—</strong>
          </div>
          <div class="sentiment-visual">
            <div id="fear-greed-gauge" class="sentiment-gauge"></div>
            <ul class="sentiment-legend">
              <li class="sentiment-legend-item" data-band="extreme-fear">
                <span class="legend-swatch" aria-hidden="true"></span>
                <div class="legend-text">
                  <span class="legend-range">0 – 25</span>
                  <span class="legend-label">Extreme Fear</span>
                </div>
              </li>
              <li class="sentiment-legend-item" data-band="fear">
                <span class="legend-swatch" aria-hidden="true"></span>
                <div class="legend-text">
                  <span class="legend-range">26 – 44</span>
                  <span class="legend-label">Fear</span>
                </div>
              </li>
              <li class="sentiment-legend-item" data-band="neutral">
                <span class="legend-swatch" aria-hidden="true"></span>
                <div class="legend-text">
                  <span class="legend-range">45 – 54</span>
                  <span class="legend-label">Neutral</span>
                </div>
              </li>
              <li class="sentiment-legend-item" data-band="greed">
                <span class="legend-swatch" aria-hidden="true"></span>
                <div class="legend-text">
                  <span class="legend-range">55 – 74</span>
                  <span class="legend-label">Greed</span>
                </div>
              </li>
              <li class="sentiment-legend-item" data-band="extreme-greed">
                <span class="legend-swatch" aria-hidden="true"></span>
                <div class="legend-text">
                  <span class="legend-range">75 – 100</span>
                  <span class="legend-label">Extreme Greed</span>
                </div>
              </li>
            </ul>
          </div>
          <p id="fear-greed-classification" class="sentiment-classification">—</p>
        </section>
        <section class="panel">
          <div class="panel-header">
            <div>
              <h2>Historique</h2>
            </div>
            <div class="range-selector" id="fear-greed-range" role="radiogroup">
              <button type="button" data-range="30d">30j</button>
              <button type="button" data-range="90d">90j</button>
              <button type="button" data-range="1y">1 an</button>
              <button type="button" data-range="max">Tout</button>
            </div>
          </div>
          <p id="history-error" hidden>Aucune donnée</p>
          <div id="fear-greed-history" class="chart-target"></div>
        </section>
      </main>
    </body></html>`,
    { url: 'https://example.test/fear-greed.html' },
  );
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  ApexChartsStub.instances = [];
  dom.window.ApexCharts = ApexChartsStub;
  document.documentElement.style.setProperty('--fg-extreme-fear', '#ef4444');
  document.documentElement.style.setProperty('--fg-fear', '#f97316');
  document.documentElement.style.setProperty('--fg-neutral', '#facc15');
  document.documentElement.style.setProperty('--fg-greed', '#22c55e');
  document.documentElement.style.setProperty('--fg-extreme-greed', '#0ea5e9');
  return dom;
}

async function importFresh(modulePath) {
  const cacheBuster = Math.random().toString(36).slice(2);
  return import(`${modulePath}?${cacheBuster}`);
}

function mockFetchSequence(responses) {
  let call = 0;
  global.fetch = async (url) => {
    const current = responses[call];
    call += 1;
    if (!current) {
      throw new Error(`unexpected fetch ${url}`);
    }
    if (typeof current === 'function') {
      return current(url);
    }
    return current;
  };
}

function createResponse(json, status = 200) {
  return new Response(JSON.stringify(json), { status, headers: { 'content-type': 'application/json' } });
}

test('fear-greed init renders gauge, legend and history chart with neutral scale', async (t) => {
  const dom = setupDom();
  const latest = { value: 58, classification: 'Greed', timestamp: '2024-03-10T00:00:00Z' };
  const history = {
    range: '90d',
    points: [
      { timestamp: '2024-01-01T00:00:00Z', value: 40, classification: 'Fear' },
      { timestamp: '2024-02-01T00:00:00Z', value: 55, classification: 'Neutral' },
    ],
  };
  mockFetchSequence([
    createResponse(latest),
    createResponse(history),
  ]);

  const module = await importFresh('./fear-greed.js');
  t.after(() => {
    dom.window.close();
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  });

  await module.init();
  assert.equal(document.getElementById('fear-greed-value').textContent, '58');
  assert.equal(document.getElementById('fear-greed-classification').textContent, 'Greed');
  assert.equal(document.getElementById('fear-greed-updated'), null);
  const legendItems = document.querySelectorAll('.sentiment-legend-item');
  assert.equal(legendItems.length, 5);
  const gauge = document.getElementById('fear-greed-gauge');
  assert.ok(gauge);
  const [gaugeChart, historyChart] = ApexChartsStub.instances;
  assert.ok(gaugeChart);
  assert.ok(historyChart);
  const valueFormatter = gaugeChart.options.plotOptions.radialBar.dataLabels.value.formatter;
  assert.equal(valueFormatter(72.6), '73');
  const historyContainer = document.getElementById('fear-greed-history');
  assert.ok(historyContainer);
  const yFormatter = historyChart.options.yaxis.labels.formatter;
  assert.equal(yFormatter(42.9), '43');
  assert.equal(historyChart.options.tooltip.y.formatter(12.4), '12');
  assert.equal(historyChart.options.yaxis.min, 0);
  assert.equal(historyChart.options.yaxis.max, 100);
  const annotations = historyChart.options.annotations?.yaxis ?? [];
  assert.equal(annotations.length, 5);
  assert.deepEqual(
    annotations.map((entry) => entry.fillColor),
    ['#ef4444', '#f97316', '#facc15', '#22c55e', '#0ea5e9'],
  );
  assert(annotations.every((entry) => entry.opacity > 0 && entry.opacity <= 1));
  assert.equal(annotations[0].y, 0);
  assert.equal(Math.round(annotations.at(-1).y2), 100);
});


test('fear-greed init shows fallback when history fails', async (t) => {
  const dom = setupDom();
  const latest = { value: 42, classification: 'Neutral', timestamp: '2024-03-10T00:00:00Z' };
  mockFetchSequence([
    createResponse(latest),
    new Response('', { status: 404 }),
  ]);

  const module = await importFresh('./fear-greed.js');
  t.after(() => {
    dom.window.close();
    delete global.window;
    delete global.document;
    delete global.localStorage;
    delete global.fetch;
  });

  await module.init();
  const errorEl = document.getElementById('history-error');
  assert.equal(errorEl.hidden, false);
  assert.match(errorEl.textContent, /Aucune donnée|Historique indisponible/);
});

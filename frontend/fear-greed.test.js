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
            <strong id="fear-greed-value">—</strong>
            <span id="fear-greed-classification">—</span>
          </div>
          <div id="fear-greed-gauge"></div>
          <p id="fear-greed-updated">—</p>
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
  dom.window.ApexCharts = ApexChartsStub;
  document.documentElement.style.setProperty('--fg-greed', '#22c55e');
  document.documentElement.style.setProperty('--fg-neutral', '#facc15');
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

test('fear-greed init renders gauge and history chart', async (t) => {
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
  assert.match(document.getElementById('fear-greed-updated').textContent, /2024-03-10/);
  const gauge = document.getElementById('fear-greed-gauge');
  assert.ok(gauge);
  const historyContainer = document.getElementById('fear-greed-history');
  assert.ok(historyContainer);
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

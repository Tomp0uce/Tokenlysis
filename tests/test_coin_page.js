import assert from 'node:assert/strict';
import test from 'node:test';
import { JSDOM } from 'jsdom';

function setupDom(url = 'https://example.com/coin.html?coin_id=bitcoin') {
  const dom = new JSDOM(`<!DOCTYPE html>
    <html lang="fr">
    <head>
      <meta name="api-url" content="/api">
      <title>Test</title>
    </head>
    <body>
      <div id="status"></div>
      <h1 id="coin-title"></h1>
      <div class="metrics-grid">
        <div class="metric-card">
          <span id="price-value"></span>
          <span id="price-updated"></span>
        </div>
        <div class="metric-card">
          <span id="market-cap-value"></span>
        </div>
        <div class="metric-card">
          <span id="volume-value"></span>
        </div>
      </div>
      <section id="categories"></section>
      <div id="range-selector">
        <button data-range="24h"></button>
        <button data-range="7d"></button>
        <button data-range="1m"></button>
        <button data-range="3m"></button>
        <button data-range="max"></button>
      </div>
      <p id="history-empty" hidden>Aucune donnée</p>
      <section>
        <svg id="price-chart" viewBox="0 0 600 260"></svg>
        <svg id="market-cap-chart" viewBox="0 0 600 260"></svg>
        <svg id="volume-chart" viewBox="0 0 600 260"></svg>
      </section>
    </body>
    </html>`, {
    url,
  });
  global.window = dom.window;
  global.document = dom.window.document;
  global.HTMLElement = dom.window.HTMLElement;
  return dom;
}

async function importFresh(modulePath) {
  const cacheBuster = Math.random().toString(36).slice(2);
  return import(`${modulePath}?${cacheBuster}`);
}

function installApexChartsStub(win) {
  const { document } = win;
  const svgNS = 'http://www.w3.org/2000/svg';
  const numberFormatter = new Intl.NumberFormat('en-US', {
    minimumFractionDigits: 0,
    maximumFractionDigits: 2,
  });

  function formatNumber(value) {
    if (value === null || value === undefined) {
      return '0';
    }
    const numeric = Number(value);
    if (!Number.isFinite(numeric)) {
      return '0';
    }
    return numberFormatter.format(numeric);
  }

  function formatDateLabel(value) {
    if (!value) return '';
    const date = new Date(value);
    if (!Number.isFinite(date.getTime())) {
      return String(value);
    }
    return date.toLocaleDateString('en-US', { month: 'short', day: '2-digit' });
  }

  class ApexChartsStub {
    constructor(element, options) {
      this.element = element;
      this.options = options || {};
      this.categories = options?.xaxis?.categories || [];
      this.series = options?.series || [];
    }

    render() {
      this.draw();
      return Promise.resolve();
    }

    updateOptions(options = {}) {
      if (options?.xaxis?.categories) {
        this.categories = options.xaxis.categories;
      }
      this.draw();
      return Promise.resolve();
    }

    updateSeries(series = []) {
      if (Array.isArray(series) && series[0]?.data) {
        this.series = series;
      }
      this.draw();
      return Promise.resolve();
    }

    draw() {
      const doc = document;
      this.element.innerHTML = '';
      const categories = Array.isArray(this.categories) ? this.categories : [];
      const data = Array.isArray(this.series?.[0]?.data)
        ? this.series[0].data.map((value) => {
            const numeric = Number(value);
            return Number.isFinite(numeric) ? numeric : null;
          })
        : [];

      const polyline = doc.createElementNS(svgNS, 'polyline');
      const points = data.map((value, index) => `${index},${value ?? 0}`).join(' ');
      polyline.setAttribute('points', points);
      this.element.appendChild(polyline);

      const markers = doc.createElementNS(svgNS, 'g');
      data.forEach((value) => {
        const circle = doc.createElementNS(svgNS, 'circle');
        const title = doc.createElementNS(svgNS, 'title');
        title.textContent = formatNumber(value ?? 0);
        circle.appendChild(title);
        markers.appendChild(circle);
      });
      this.element.appendChild(markers);

      const axisX = doc.createElementNS(svgNS, 'g');
      axisX.setAttribute('class', 'axis axis-x');
      axisX.appendChild(doc.createElementNS(svgNS, 'line'));
      this.element.appendChild(axisX);

      const axisY = doc.createElementNS(svgNS, 'g');
      axisY.setAttribute('class', 'axis axis-y');
      axisY.appendChild(doc.createElementNS(svgNS, 'line'));
      this.element.appendChild(axisY);

      if (categories.length) {
        const axisXMin = doc.createElementNS(svgNS, 'text');
        axisXMin.setAttribute('data-role', 'axis-x-min');
        axisXMin.setAttribute('data-value', categories[0]);
        axisXMin.textContent = formatDateLabel(categories[0]);
        this.element.appendChild(axisXMin);

        const axisXMax = doc.createElementNS(svgNS, 'text');
        axisXMax.setAttribute('data-role', 'axis-x-max');
        axisXMax.setAttribute('data-value', categories[categories.length - 1]);
        axisXMax.textContent = formatDateLabel(categories[categories.length - 1]);
        this.element.appendChild(axisXMax);

        categories.slice(1, -1).forEach((value) => {
          const tick = doc.createElementNS(svgNS, 'text');
          tick.setAttribute('data-role', 'axis-x-tick');
          tick.textContent = formatDateLabel(value);
          axisX.appendChild(tick);
        });
      }

      const numericValues = data.filter((value) => typeof value === 'number');
      if (numericValues.length) {
        const min = Math.min(...numericValues);
        const max = Math.max(...numericValues);

        const axisYMin = doc.createElementNS(svgNS, 'text');
        axisYMin.setAttribute('data-role', 'axis-y-min');
        axisYMin.setAttribute('data-value', String(min));
        axisYMin.textContent = formatNumber(min);
        this.element.appendChild(axisYMin);

        const axisYMax = doc.createElementNS(svgNS, 'text');
        axisYMax.setAttribute('data-role', 'axis-y-max');
        axisYMax.setAttribute('data-value', String(max));
        axisYMax.textContent = formatNumber(max);
        this.element.appendChild(axisYMax);

        const tick = doc.createElementNS(svgNS, 'text');
        tick.setAttribute('data-role', 'axis-y-tick');
        tick.textContent = formatNumber((min + max) / 2);
        axisY.appendChild(tick);
      }
    }
  }

  win.ApexCharts = ApexChartsStub;
  return ApexChartsStub;
}

test('init loads coin data, renders charts and activates default range', async (t) => {
  const dom = setupDom();
  const originalDateNow = Date.now;
  Date.now = () => new Date('2024-09-20T12:00:00Z').getTime();
  installApexChartsStub(dom.window);
  const responses = {
    detail: {
      coin_id: 'bitcoin',
      vs_currency: 'usd',
      price: 44000.1234,
      market_cap: 850000000000,
      volume_24h: 15000000000,
      snapshot_at: '2024-09-20T00:00:00Z',
    },
    history: {
      max: {
        coin_id: 'bitcoin',
        vs_currency: 'usd',
        range: 'max',
        points: [
          {
            snapshot_at: '2024-09-12T00:00:00Z',
            price: 40000,
            market_cap: 810000000000,
            volume_24h: 11000000000,
          },
          {
            snapshot_at: '2024-09-16T00:00:00Z',
            price: 43000,
            market_cap: 840000000000,
            volume_24h: 12500000000,
          },
          {
            snapshot_at: '2024-09-20T00:00:00Z',
            price: 44000,
            market_cap: 850000000000,
            volume_24h: 15000000000,
          },
        ],
      },
      '7d': {
        coin_id: 'bitcoin',
        vs_currency: 'usd',
        range: '7d',
        points: [
          {
            snapshot_at: '2024-09-14T00:00:00Z',
            price: 42000,
            market_cap: 830000000000,
            volume_24h: 12000000000,
          },
          {
            snapshot_at: '2024-09-17T00:00:00Z',
            price: 43500,
            market_cap: 840000000000,
            volume_24h: 13000000000,
          },
          {
            snapshot_at: '2024-09-20T00:00:00Z',
            price: 44000,
            market_cap: 850000000000,
            volume_24h: 15000000000,
          },
        ],
      },
    },
  };
  const fetchCalls = [];
  global.fetch = async (url) => {
    fetchCalls.push(url);
    if (url.endsWith('/api/price/bitcoin')) {
      return new Response(JSON.stringify(responses.detail), { status: 200 });
    }
    if (url.includes('/api/price/bitcoin/history')) {
      const parsed = new URL(url, 'https://example.com');
      const range = parsed.searchParams.get('range');
      const payload = responses.history[range];
      if (!payload) {
        throw new Error(`missing history for range ${range}`);
      }
      return new Response(JSON.stringify(payload), { status: 200 });
    }
    throw new Error(`unexpected fetch ${url}`);
  };
  const module = await importFresh('../frontend/coin.js');
  t.after(() => {
    dom.window.close();
    delete global.fetch;
    delete global.window;
    delete global.document;
    delete global.HTMLElement;
    Date.now = originalDateNow;
  });
  await module.init();
  assert.equal(fetchCalls[0].endsWith('/api/price/bitcoin'), true);
  assert.equal(
    fetchCalls.some((url) => url.includes('/api/price/bitcoin/history') && url.includes('range=max')),
    true,
  );
  assert.equal(
    fetchCalls.some((url) => url.includes('/api/price/bitcoin/history') && url.includes('range=7d')),
    true
  );
  assert.equal(document.getElementById('coin-title').textContent.includes('Bitcoin'), true);
  assert.equal(document.getElementById('price-value').textContent.includes('44,000'), true);
  assert.equal(document.getElementById('market-cap-value').textContent, '850 B$');
  assert.equal(document.getElementById('volume-value').textContent, '15 B$');
  assert.match(
    document.getElementById('price-updated').textContent,
    /Dernière mise à jour/
  );
  const activeButton = document.querySelector('[data-range="7d"]');
  assert.equal(activeButton.classList.contains('active'), true);
  const pricePoints = document.querySelector('#price-chart polyline').getAttribute('points');
  assert.notEqual(pricePoints, '');
  const marketPoints = document
    .querySelector('#market-cap-chart polyline')
    .getAttribute('points');
  assert.notEqual(marketPoints, '');
  const volumePoints = document.querySelector('#volume-chart polyline').getAttribute('points');
  assert.notEqual(volumePoints, '');
  assert.ok(document.querySelector('#price-chart .axis.axis-x line'));
  assert.ok(document.querySelector('#price-chart .axis.axis-y line'));
  const axisXMin = document.querySelector('#price-chart text[data-role="axis-x-min"]');
  assert.ok(axisXMin);
  assert.equal(axisXMin.getAttribute('data-value'), '2024-09-14T00:00:00Z');
  assert.equal(axisXMin.textContent, 'Sep 14');
  const axisXMax = document.querySelector('#price-chart text[data-role="axis-x-max"]');
  assert.ok(axisXMax);
  assert.equal(axisXMax.getAttribute('data-value'), '2024-09-20T00:00:00Z');
  assert.equal(axisXMax.textContent, 'Sep 20');
  const axisYMin = document.querySelector('#price-chart text[data-role="axis-y-min"]');
  assert.ok(axisYMin);
  assert.equal(axisYMin.getAttribute('data-value'), '42000');
  assert.equal(axisYMin.textContent, '42,000');
  const axisYMax = document.querySelector('#price-chart text[data-role="axis-y-max"]');
  assert.ok(axisYMax);
  assert.equal(axisYMax.getAttribute('data-value'), '44000');
  assert.equal(axisYMax.textContent, '44,000');
  const intermediateYTicks = document.querySelectorAll(
    '#price-chart text[data-role="axis-y-tick"]'
  );
  assert.ok(intermediateYTicks.length >= 1);
  const intermediateXTicks = document.querySelectorAll(
    '#price-chart text[data-role="axis-x-tick"]'
  );
  assert.ok(intermediateXTicks.length >= 1);
  assert.equal(document.getElementById('history-empty').hidden, true);
});

test('clicking a range button refetches history and updates active state', async (t) => {
  const dom = setupDom();
  const originalDateNow = Date.now;
  Date.now = () => new Date('2024-09-20T00:00:00Z').getTime();
  installApexChartsStub(dom.window);
  const historyPayloads = {
    max: {
      coin_id: 'bitcoin',
      vs_currency: 'usd',
      range: 'max',
      points: [
        {
          snapshot_at: '2024-09-12T00:00:00Z',
          price: 1,
          market_cap: 2,
          volume_24h: 3,
        },
        {
          snapshot_at: '2024-09-16T00:00:00Z',
          price: 2,
          market_cap: 3,
          volume_24h: 4,
        },
        {
          snapshot_at: '2024-09-20T00:00:00Z',
          price: 3,
          market_cap: 4,
          volume_24h: 5,
        },
      ],
    },
    '7d': {
      coin_id: 'bitcoin',
      vs_currency: 'usd',
      range: '7d',
      points: [
        {
          snapshot_at: '2024-09-14T00:00:00Z',
          price: 1,
          market_cap: 2,
          volume_24h: 3,
        },
        {
          snapshot_at: '2024-09-15T00:00:00Z',
          price: 2,
          market_cap: 3,
          volume_24h: 4,
        },
      ],
    },
    '24h': {
      coin_id: 'bitcoin',
      vs_currency: 'usd',
      range: '24h',
      points: [
        {
          snapshot_at: '2024-09-19T12:00:00Z',
          price: 3,
          market_cap: 4,
          volume_24h: 5,
        },
        {
          snapshot_at: '2024-09-20T00:00:00Z',
          price: 4,
          market_cap: 5,
          volume_24h: 6,
        },
      ],
    },
  };
  const fetchCalls = [];
  global.fetch = async (url) => {
    fetchCalls.push(url);
    if (url.endsWith('/api/price/bitcoin')) {
      return new Response(
        JSON.stringify({
          coin_id: 'bitcoin',
          vs_currency: 'usd',
          price: 4,
          market_cap: 5,
          volume_24h: 6,
          snapshot_at: '2024-09-20T00:00:00Z',
        }),
        { status: 200 }
      );
    }
    if (url.includes('/api/price/bitcoin/history')) {
      const parsed = new URL(url, 'https://example.com');
      const range = parsed.searchParams.get('range');
      const payload = historyPayloads[range];
      if (!payload) {
        throw new Error(`missing history for range ${range}`);
      }
      return new Response(JSON.stringify(payload), { status: 200 });
    }
    throw new Error(`unexpected fetch ${url}`);
  };
  const module = await importFresh('../frontend/coin.js');
  t.after(() => {
    dom.window.close();
    delete global.fetch;
    delete global.window;
    delete global.document;
    delete global.HTMLElement;
    Date.now = originalDateNow;
  });
  await module.init();
  const originalTitles = [
    ...document.querySelectorAll('#price-chart circle title')
  ].map((node) => node.textContent);
  const originalAxisYMax = document
    .querySelector('#price-chart text[data-role="axis-y-max"]')
    .getAttribute('data-value');
  const originalAxisXMin = document
    .querySelector('#price-chart text[data-role="axis-x-min"]')
    .getAttribute('data-value');
  const button24h = document.querySelector('[data-range="24h"]');
  button24h.dispatchEvent(new window.Event('click', { bubbles: true }));
  await new Promise((resolve) => setTimeout(resolve, 0));
  assert.equal(
    fetchCalls.some((url) =>
      url.includes('/api/price/bitcoin/history') && url.includes('range=24h')
    ),
    true
  );
  assert.equal(button24h.classList.contains('active'), true);
  const updatedTitles = [
    ...document.querySelectorAll('#price-chart circle title')
  ].map((node) => node.textContent);
  assert.notDeepEqual(originalTitles, updatedTitles);
  const updatedAxisYMax = document
    .querySelector('#price-chart text[data-role="axis-y-max"]')
    .getAttribute('data-value');
  const updatedAxisXMin = document
    .querySelector('#price-chart text[data-role="axis-x-min"]')
    .getAttribute('data-value');
  assert.notEqual(originalAxisYMax, updatedAxisYMax);
  assert.notEqual(originalAxisXMin, updatedAxisXMin);
});

test('init reports error when coin_id is missing', async (t) => {
  const dom = setupDom('https://example.com/coin.html');
  let fetchUsed = false;
  global.fetch = async () => {
    fetchUsed = true;
    throw new Error('should not fetch');
  };
  const module = await importFresh('../frontend/coin.js');
  t.after(() => {
    dom.window.close();
    delete global.fetch;
    delete global.window;
    delete global.document;
    delete global.HTMLElement;
  });
  await module.init();
  assert.equal(fetchUsed, false);
  assert.match(document.getElementById('status').textContent, /Aucune crypto sélectionnée/);
});

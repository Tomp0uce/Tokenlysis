import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';

const themeCssUrl = new URL('./theme.css', import.meta.url);
const indexHtmlUrl = new URL('./index.html', import.meta.url);

async function readThemeCss() {
  return readFile(themeCssUrl, 'utf8');
}

test('summary metrics stack vertically to free sentiment space', async () => {
  const css = await readThemeCss();
  const summaryRule = css.match(/\.summary-grid\s*\{[^}]*\}/s);
  assert.ok(summaryRule, 'summary-grid styles should be defined');
  assert.match(
    summaryRule[0],
    /grid-template-columns:\s*minmax\(0,\s*1fr\);/,
    'summary-grid should use a single column layout',
  );
  assert.ok(
    !/\.summary-grid[^}]*repeat\(auto-fit/i.test(summaryRule[0]),
    'summary-grid should not use auto-fit columns anymore',
  );
});

test('desktop hero layout reserves wider column for sentiment panel', async () => {
  const css = await readThemeCss();
  const mediaBlock = css.match(/@media\s*\(min-width:\s*960px\)\s*\{[^}]*\.hero-insights\s*\{[^}]*\}[^}]*\}/s);
  assert.ok(mediaBlock, 'hero-insights media query should exist');
  assert.match(
    mediaBlock[0],
    /grid-template-columns:\s*minmax\(280px,\s*320px\)\s*minmax\(0,\s*1fr\);/,
    'desktop layout should limit metrics width and expand sentiment area',
  );
});

test('sentiment gauge has increased minimum height for better readability', async () => {
  const css = await readThemeCss();
  const gaugeRule = css.match(/\.sentiment-gauge\s*\{[^}]*\}/s);
  assert.ok(gaugeRule, 'sentiment-gauge styles should exist');
  assert.match(
    gaugeRule[0],
    /min-height:\s*26\dpx;/,
    'sentiment gauge should allocate at least 260px height',
  );
});

test('dashboard does not include Kickmaker intro overlay markup or styles', async () => {
  const [html, css] = await Promise.all([
    readFile(indexHtmlUrl, 'utf8'),
    readThemeCss(),
  ]);

  assert.ok(
    !/kickmaker-logo\.png/i.test(html),
    'index.html should not preload or reference the Kickmaker logo',
  );
  assert.ok(
    !/<div\s+id="intro"/i.test(html),
    'index.html should not render the Kickmaker intro overlay container',
  );
  assert.ok(
    !/\.intro\b/.test(css),
    'theme.css should not declare intro overlay styles',
  );
});

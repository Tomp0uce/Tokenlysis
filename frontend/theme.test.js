import test from 'node:test';
import assert from 'node:assert/strict';
import { JSDOM } from 'jsdom';

test('applyTheme sets attribute, color-scheme and notifies subscribers', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.matchMedia = () => ({ matches: false, addEventListener() {}, removeEventListener() {} });

  const module = await import('./theme.js');
  let observed = '';
  module.onThemeChange((theme) => {
    observed = theme;
  });

  module.applyTheme('dark');

  assert.equal(document.documentElement.dataset.theme, 'dark');
  assert.equal(document.documentElement.style.colorScheme, 'dark');
  assert.equal(observed, 'dark');
  assert.equal(localStorage.getItem('tokenlysis-theme'), 'dark');
});

test('getInitialTheme falls back to light on unknown preference', async () => {
  const dom = new JSDOM('<!doctype html><html><body></body></html>', { url: 'http://localhost' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.localStorage = dom.window.localStorage;
  dom.window.matchMedia = (query) => ({
    media: query,
    matches: true,
    addEventListener() {},
    removeEventListener() {},
  });

  const module = await import('./theme.js');
  localStorage.setItem('tokenlysis-theme', 'not-a-theme');
  const theme = module.getInitialTheme();
  assert.equal(theme, 'dark');
});

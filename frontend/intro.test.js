import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { JSDOM } from 'jsdom';

let importCounter = 0;

async function loadIntroModule() {
  const moduleUrl = new URL('./intro.js', import.meta.url);
  moduleUrl.searchParams.set('test', String(importCounter += 1));
  await import(moduleUrl);
}

function createDom({ prefersReduced = false, introSeen = false, complete = true } = {}) {
  const html = `<!doctype html><html><head></head><body>
    <div id="intro" class="intro" aria-hidden="true">
      <div class="intro__bg"></div>
      <div class="intro__logo-wrap">
        <img id="intro-logo" class="intro__logo" src="./assets/kickmaker-logo.png" alt="Kickmaker">
      </div>
    </div>
  </body></html>`;
  const dom = new JSDOM(html, { url: 'https://example.test' });
  global.window = dom.window;
  global.document = dom.window.document;
  global.sessionStorage = dom.window.sessionStorage;
  global.matchMedia = dom.window.matchMedia;

  if (introSeen) {
    sessionStorage.setItem('introSeen', '1');
  }

  window.matchMedia = () => ({ matches: prefersReduced, media: '', onchange: null, addListener() {}, removeListener() {}, addEventListener() {}, removeEventListener() {}, dispatchEvent() { return false; } });

  const logo = document.getElementById('intro-logo');
  Object.defineProperty(logo, 'complete', {
    configurable: true,
    get() {
      return complete;
    },
  });

  const timers = [];
  const originalSetTimeout = global.setTimeout;
  global.setTimeout = (fn, delay = 0) => {
    timers.push({ fn, delay });
    return timers.length;
  };

  return {
    dom,
    logo,
    flushTimers() {
      while (timers.length > 0) {
        const { fn } = timers.shift();
        fn();
      }
    },
    restore() {
      global.setTimeout = originalSetTimeout;
      delete global.window;
      delete global.document;
      delete global.sessionStorage;
      delete global.matchMedia;
    },
  };
}

test('index.html précharge le logo et inclut le script intro', async () => {
  const file = await readFile(new URL('./index.html', import.meta.url), 'utf8');
  assert.match(file, /<link rel="preload" href="\.\/assets\/kickmaker-logo\.png" as="image">/);
  assert.match(file, /<div id="intro" class="intro" aria-hidden="true">/);
  assert.match(file, /<script defer src="\.\/intro\.js"><\/script>/);
});

test('theme.css contient les styles de l\'intro', async () => {
  const css = await readFile(new URL('./theme.css', import.meta.url), 'utf8');
  assert.match(css, /\/\* === Kickmaker Intro === \*\//);
  assert.match(css, /\.intro\s*\{/);
  assert.match(css, /@keyframes overlay-out/);
});

test('prefers-reduced-motion masque immédiatement l\'intro', async () => {
  const context = createDom({ prefersReduced: true });
  await loadIntroModule();
  const overlay = document.getElementById('intro');
  assert.equal(overlay.hidden, true);
  assert(document.documentElement.classList.contains('intro-done'));
  context.restore();
});

test('sessionStorage empêche une réexécution', async () => {
  const context = createDom({ introSeen: true });
  await loadIntroModule();
  const overlay = document.getElementById('intro');
  assert.equal(overlay.hidden, true);
  assert(document.documentElement.classList.contains('intro-done'));
  context.restore();
});

test('l\'intro joue puis retire l\'overlay', async () => {
  const context = createDom();
  await loadIntroModule();
  const overlay = document.getElementById('intro');
  assert(overlay.classList.contains('intro--play'));
  context.flushTimers();
  assert(overlay.classList.contains('intro--out'));
  assert(document.documentElement.classList.contains('intro-done'));
  assert.equal(sessionStorage.getItem('introSeen'), '1');
  // la suppression a lieu dans un dernier setTimeout
  context.flushTimers();
  assert.equal(document.getElementById('intro'), null);
  context.restore();
});

test('une erreur de chargement masque l\'overlay', async () => {
  const context = createDom({ complete: false });
  await loadIntroModule();
  const overlay = document.getElementById('intro');
  const logo = document.getElementById('intro-logo');
  logo.dispatchEvent(new window.Event('error'));
  assert.equal(overlay.hidden, true);
  assert(document.documentElement.classList.contains('intro-done'));
  context.restore();
});

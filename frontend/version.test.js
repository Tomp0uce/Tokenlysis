import test from 'node:test';
import assert from 'node:assert/strict';
import { getAppVersion } from './version.js';

// T4: window.APP_VERSION is used when defined
test('getAppVersion returns window.APP_VERSION when set', () => {
  delete process.env.APP_VERSION;
  delete process.env.NEXT_PUBLIC_APP_VERSION;
  global.window = { APP_VERSION: '1.2.3' };
  assert.equal(getAppVersion(), '1.2.3');
  delete global.window;
});

// T5: defaults to dev when nothing provided
test('getAppVersion returns dev when no sources define version', () => {
  delete process.env.APP_VERSION;
  delete process.env.NEXT_PUBLIC_APP_VERSION;
  delete global.window;
  assert.equal(getAppVersion(), 'dev');
});

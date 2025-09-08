import test from 'node:test';
import assert from 'node:assert/strict';
import { resolveVersion } from './utils.js';

// T1: API version wins when not 'dev'
test('resolveVersion prioritizes API version when provided and not dev', () => {
  assert.equal(resolveVersion('1.2.3', '0.0.1'), '1.2.3');
});

// T2: Local version used when API version is 'dev'
test("resolveVersion falls back to local version when API version is 'dev'", () => {
  assert.equal(resolveVersion('dev', '1.2.3'), '1.2.3');
});

// T3: Default to 'dev' when neither source provides a version
test('resolveVersion returns dev when both versions are missing', () => {
  assert.equal(resolveVersion(null, null), 'dev');
});

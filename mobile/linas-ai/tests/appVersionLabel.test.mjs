/**
 * In-app Version is the native EAS build, not stale app.json 1.0.0 / 23.
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function readSrc(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

test('config reads native IPA/AAB version fields from expo-application', () => {
  const config = readSrc('config.ts');
  const pkg = readFileSync(join(root, 'package.json'), 'utf8');
  assert.match(pkg, /"expo-application"/);
  assert.match(config, /from 'expo-application'/);
  assert.match(config, /nativeApplicationVersion/);
  assert.match(config, /nativeBuildVersion/);
  assert.match(config, /APP_VERSION_LABEL = `Linas \$\{APP_BUILD_LABEL\}`/);
  assert.doesNotMatch(config, /expoConfig\?\.ios\?\.buildNumber/);
  assert.doesNotMatch(config, /expoConfig\?\.android\?\.versionCode/);
});

test('Settings and drawer copy use the auto-incrementing native build', () => {
  const en = readSrc('i18n/locales/settingsUiEn.ts');
  const ar = readSrc('i18n/locales/settingsUiAr.ts');
  const fr = readSrc('i18n/locales/settingsUiFr.ts');
  assert.match(en, /Linas AI • Version \{build\}/);
  assert.doesNotMatch(en, /\{version\}/);
  assert.match(ar, /الإصدار \{build\}/);
  assert.doesNotMatch(ar, /\{version\}/);
  assert.match(fr, /Version \{build\}/);
  assert.doesNotMatch(fr, /\{version\}/);
});

/**
 * Fails if ar/fr locale tables miss English keys, or welcome chips lack locale coverage.
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function extractKeys(source) {
  const keys = new Set();
  for (const m of source.matchAll(/^\s{2}([A-Za-z][A-Za-z0-9_]*)\s*:/gm)) {
    keys.add(m[1]);
  }
  return keys;
}

const CRITICAL_KEYS = [
  'chatEmptyTitle',
  'chatEmptyBody',
  'welcomeQuickStart',
  'welcomeChipLearnApp',
  'welcomeChipSetupGuided',
  'welcomeChipSetupBulk',
  'welcomeChipConnectMeta',
  'welcomeChipCheckPlan',
  'welcomeChipModeWork',
  'welcomeChipModeChat',
  'composerPlaceholder',
  'composerPlaceholderChat',
  'composerPlaceholderWork',
  'guestHowCanHelp',
  'guestStarterWhatTitle',
  'loginWelcome',
  'subscribeGateTitle',
  'authGateHardTitle',
  'navContentManagement',
];

test('ar and fr locale tables include every English key', () => {
  const en = readFileSync(join(root, 'src/i18n/locales/en.ts'), 'utf8');
  const ar = readFileSync(join(root, 'src/i18n/locales/ar.ts'), 'utf8');
  const fr = readFileSync(join(root, 'src/i18n/locales/fr.ts'), 'utf8');
  const enKeys = extractKeys(en);
  const arKeys = extractKeys(ar);
  const frKeys = extractKeys(fr);
  assert.ok(enKeys.size > 50, 'expected substantial English key set');
  const missingAr = [...enKeys].filter((k) => !arKeys.has(k)).sort();
  const missingFr = [...enKeys].filter((k) => !frKeys.has(k)).sort();
  assert.deepEqual(missingAr, [], `missing ar keys: ${missingAr.join(', ')}`);
  assert.deepEqual(missingFr, [], `missing fr keys: ${missingFr.join(', ')}`);
});

test('critical welcome/composer/auth keys exist in en/ar/fr', () => {
  const en = extractKeys(readFileSync(join(root, 'src/i18n/locales/en.ts'), 'utf8'));
  const ar = extractKeys(readFileSync(join(root, 'src/i18n/locales/ar.ts'), 'utf8'));
  const fr = extractKeys(readFileSync(join(root, 'src/i18n/locales/fr.ts'), 'utf8'));
  for (const key of CRITICAL_KEYS) {
    assert.ok(en.has(key), `en missing ${key}`);
    assert.ok(ar.has(key), `ar missing ${key}`);
    assert.ok(fr.has(key), `fr missing ${key}`);
  }
});

test('OwnerWelcomeChips and chip data use i18n label keys', () => {
  const chipsUi = readFileSync(join(root, 'src/features/chat/OwnerWelcomeChips.tsx'), 'utf8');
  const chipData = readFileSync(join(root, 'src/features/chat/ownerWelcomeChipData.ts'), 'utf8');
  assert.match(chipsUi, /useI18n/);
  assert.match(chipsUi, /welcomeQuickStart/);
  assert.match(chipData, /labelKey:\s*'welcomeChipLearnApp'/);
  assert.match(chipData, /labelKey:\s*'welcomeChipSetupGuided'/);
  assert.doesNotMatch(chipsUi, /Quick start/);
  assert.doesNotMatch(chipData, /label:\s*'Want to learn/);
});

test('API client and owner stream send Accept-Language / reply_language', () => {
  const client = readFileSync(join(root, 'src/api/client.ts'), 'utf8');
  const stream = readFileSync(join(root, 'src/features/chat/v2/useOwnerStream.ts'), 'utf8');
  const session = readFileSync(join(root, 'src/features/chat/useChatSession.ts'), 'utf8');
  assert.match(client, /Accept-Language/);
  assert.match(stream, /Accept-Language/);
  assert.match(stream, /reply_language/);
  assert.match(session, /language:\s*getStoredAppLanguage\(\)/);
});

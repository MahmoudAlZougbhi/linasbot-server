/**
 * First-open AI Setup lists share Knowledge chrome: title, subtitle, search + add square.
 * Run: node --test mobile/linas-ai/tests/aiSetupListChrome.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

const LISTS = [
  'features/cm/knowledge/KnowledgeListView.tsx',
  'features/cm/editors/locationOpeningHours/BranchListView.tsx',
  'features/services/ServiceListView.tsx',
  'features/cm/comments/CommentListView.tsx',
  'features/cm/requestRules/RequestRuleListView.tsx',
  'features/products/ProductListView.tsx',
  'features/faq/FaqListView.tsx',
];

describe('AI Setup first-open list chrome', () => {
  it('shared header is title, subtitle, search, and a teal plus square', () => {
    const header = read('features/cm/AiSetupListHeader.tsx');
    assert.doesNotMatch(header, /styles\.hero/);
    assert.match(header, /feather\('search'\)/);
    assert.match(header, /feather\('plus'\)/);
    assert.match(header, /styles\.addSq/);
    assert.match(header, /AI_SETUP_TEAL/);
    assert.doesNotMatch(header, /PrimaryButton/);
    assert.doesNotMatch(header, /sparkles-outline/);
  });

  it('every setup list uses the shared header', () => {
    for (const rel of LISTS) {
      const src = read(rel);
      assert.match(src, /AiSetupListHeader/, rel);
      assert.doesNotMatch(src, /PrimaryButton/, rel);
    }
  });

  it('ScreenChrome keeps back and title on one compact row', () => {
    const chrome = read('features/shared/ScreenChrome.tsx');
    assert.match(chrome, /compactTitle/);
    assert.match(chrome, /styles\.navTitle/);
    assert.match(chrome, /headerRowCompact/);
    assert.doesNotMatch(chrome, /stackedHeader && styles\.hero/);
  });

  it('Knowledge subtitle and footer use the Linas sparkle mark', () => {
    const en = read('i18n/locales/aiSetupEn.ts');
    const list = read('features/cm/knowledge/KnowledgeListView.tsx');
    assert.match(en, /knowledgeSubtitle: 'Teach Linas AI about your business'/);
    assert.match(list, /LinasSparkleIcon/);
    assert.doesNotMatch(list, /sparkles-outline/);
    assert.doesNotMatch(list, /ion\(/);
  });
});

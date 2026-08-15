/**
 * Smart Q&A list screen design-handoff checks (no device required).
 * Run: node --test mobile/linas-ai/tests/*.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);

function read(rel) {
  return readFileSync(src(...rel.split('/')), 'utf8');
}

test('Smart Q&A list matches screenshot handoff', () => {
  const screen = read('features/faq/FaqScreen.tsx');
  const list = read('features/faq/FaqListView.tsx');
  const banner = read('features/faq/FaqInfoBanner.tsx');
  const langs = read('features/faq/FaqLanguagesCard.tsx');
  const toolbar = read('features/faq/FaqListToolbar.tsx');
  const card = read('features/faq/FaqQaCard.tsx');
  const chrome = read('features/faq/faqChrome.ts');
  const en = read('i18n/locales/en.ts');
  const faqEn = read('i18n/locales/faqUiEn.ts');
  const faqAr = read('i18n/locales/faqUiAr.ts');
  const faqFr = read('i18n/locales/faqUiFr.ts');

  assert.match(screen, /title=\{tr\('faqTitle'\)\}/);
  assert.doesNotMatch(screen, /subtitle=\{tr\('faqSub'\)\}/);
  assert.match(en, /faqTitle:\s*'Smart Q&A'/);
  assert.match(en, /faqCreateNew:\s*'Create Q&A'/);
  assert.match(en, /faqWhyTitle:\s*'Save credits with Smart Q&A'/);
  assert.doesNotMatch(en, /Smart Answers/);
  assert.doesNotMatch(faqEn, /Smart Answers/);

  assert.match(chrome, /FAQ_TEAL = '#007A7C'/);
  assert.match(chrome, /FAQ_BORDER = '#E2E8F0'/);
  assert.match(chrome, /FAQ_RADIUS = 12/);
  assert.match(banner, /LinasSparkleIcon/);
  assert.match(banner, /FAQ_TEAL/);
  assert.match(banner, /tr\('faqWhyTitle'\)/);

  assert.match(list, /tr\('faqCreateNew'\)/);
  assert.match(list, /plusCircle/);
  assert.doesNotMatch(list, /faqAskLinas/);
  assert.doesNotMatch(list, /onAskLinas/);
  assert.doesNotMatch(list, /tr\('retry'\)/);
  assert.doesNotMatch(list, /12 answers/);

  assert.match(faqEn, /faqLangSection:\s*'Q&A languages'/);
  assert.match(langs, /tr\('faqAddLanguage'\)/);
  assert.match(langs, /langNativeLabel/);
  assert.match(langs, /chipOn/);
  assert.match(langs, /onRemoveLanguage/);
  assert.doesNotMatch(langs, /onLongPress/);

  assert.match(toolbar, /\{count\} \{tr\('faqAnswersCount'\)\}/);
  assert.match(toolbar, /feather\('search'\)/);
  assert.match(toolbar, /FAQ_ICON_SQ/);

  assert.match(card, /faqQuestionLabel/);
  assert.match(card, /faqAnswerLabel/);
  assert.match(card, /toUpperCase/);
  assert.match(card, /height: 1/);
  assert.match(card, /faqTranslatedStatus/);
  assert.match(card, /feather\('edit-2'\)/);
  assert.match(card, /feather\('trash-2'\)/);
  assert.match(card, /FAQ_TEAL/);

  assert.match(faqEn, /Translated to selected languages/);
  assert.match(faqAr, /مترجم إلى اللغات المختارة/);
  assert.match(faqFr, /Traduit dans les langues sélectionnées/);
  assert.match(screen, /archiveFaq/);
  assert.match(screen, /confirmDelete/);
});

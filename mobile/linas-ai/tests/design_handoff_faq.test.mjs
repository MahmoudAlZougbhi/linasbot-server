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
  const card = read('features/faq/FaqQaCard.tsx');
  const chrome = read('features/faq/faqChrome.ts');
  const en = read('i18n/locales/en.ts');
  const faqEn = read('i18n/locales/faqUiEn.ts');
  const faqAr = read('i18n/locales/faqUiAr.ts');
  const faqFr = read('i18n/locales/faqUiFr.ts');

  assert.match(screen, /title=\{tr\('faqTitle'\)\}/);
  assert.match(screen, /subtitle=\{mode === 'list' \? tr\('faqSub'\) : undefined\}/);
  assert.match(en, /faqTitle:\s*'Smart Q&A'/);
  assert.match(en, /faqSub:\s*'Translate Q&A into any language you choose\.'/);
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
  assert.match(list, /AiSetupListHeader/);
  assert.doesNotMatch(list, /plusCircle/);
  assert.doesNotMatch(list, /PrimaryButton/);
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

  assert.match(list, /faqAnswersCount/);
  assert.match(list, /faqSearchPlaceholder/);

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
  assert.match(screen, /deleteSmartAnswerLanguage/);
  assert.match(faqEn, /faqRemoveLangTitle/);
  assert.match(faqAr, /إزالة اللغة/);
  assert.match(faqFr, /Retirer la langue/);

  const langsTs = read('features/faq/faqLanguages.ts');
  const iso = read('features/faq/iso639Languages.ts');
  assert.match(langsTs, /ISO639_LANGUAGE_CATALOG/);
  assert.match(iso, /id: 'zh'/);
  assert.match(iso, /id: 'aa'/);
  assert.ok((iso.match(/id: '/g) || []).length >= 180);
});

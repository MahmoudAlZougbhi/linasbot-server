/**
 * AI Basics screenshot handoff — tabs, greetings list/edit, draft wiring.
 * Run: node --test mobile/linas-ai/tests/aiBasicsScreen.design.test.mjs
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

describe('AI Basics screens match screenshot handoff', () => {
  it('uses Identity / Style & Tone / Greetings tabs and Save changes', () => {
    const screen = read('features/cm/aiBasics/AiBasicsScreen.tsx');
    const tabs = read('features/cm/aiBasics/AiBasicsTabBar.tsx');
    const en = read('i18n/locales/aiSetupEn.ts');
    assert.match(en, /aiSetupBasicsSubtitle: 'Define who Linas is and how it communicates\.'/);
    assert.match(en, /aiSetupBasicsStyleTab: 'Style & Tone'/);
    assert.match(en, /aiSetupSaveChanges: 'Save changes'/);
    assert.match(tabs, /identity.*style.*greetings/s);
    assert.match(screen, /AiBasicsTabBar/);
    assert.match(screen, /tr\('aiSetupSaveChanges'\)/);
    assert.match(screen, /tab !== 'greetings'/);
  });

  it('identity and style fields match the design', () => {
    const identity = read('features/cm/aiBasics/AiBasicsIdentityTab.tsx');
    const style = read('features/cm/aiBasics/AiBasicsStyleTab.tsx');
    const en = read('i18n/locales/aiSetupEn.ts');
    assert.match(en, /aiSetupShortIntro: 'Introduction for Linas'/);
    assert.match(en, /aiSetupStyleNoteHint: 'Use this only for extra guidance\.'/);
    assert.match(en, /aiSetupAiRolePlaceholder: 'e\.g\. Front desk assistant'/);
    assert.match(identity, /aiSetupBasicsPurposeHeading/);
    assert.match(identity, /clinic_name/);
    assert.match(identity, /short_introduction/);
    assert.match(style, /STYLE_TONE/);
    assert.match(style, /STYLE_FORMALITY/);
    assert.match(style, /STYLE_EMOJI/);
    assert.match(style, /AiBasicsSegmented/);
  });

  it('greetings list has search, add, Active badge, and footer tip', () => {
    const list = read('features/cm/aiBasics/AiBasicsGreetingsList.tsx');
    const card = read('features/cm/aiBasics/GreetingCard.tsx');
    const en = read('i18n/locales/aiSetupEn.ts');
    assert.match(en, /aiSetupGreetingsSearch: 'Search greetings\.'/);
    assert.match(en, /aiSetupGreetingsFooter: 'Tap a rule to view, edit, or delete it\.'/);
    assert.match(en, /aiSetupGreetingActive: 'Active'/);
    assert.match(list, /AiSetupListHeader/);
    assert.match(list, /aiSetupGreetingsFooter/);
    assert.match(card, /message-circle/);
    assert.match(card, /activeLabel/);
    assert.match(card, /item\.enabled/);
  });

  it('add greeting has note word count, resources, and Save greeting', () => {
    const edit = read('features/cm/aiBasics/GreetingEditView.tsx');
    const screen = read('features/cm/aiBasics/AiBasicsScreen.tsx');
    const en = read('i18n/locales/aiSetupEn.ts');
    assert.match(en, /aiSetupAddGreeting: 'Add greeting'/);
    assert.match(en, /aiSetupSaveGreeting: 'Save greeting'/);
    assert.match(en, /aiSetupGreetingNoteHelper:/);
    assert.match(en, /aiSetupGreetingResourcesHint:/);
    assert.match(edit, /countWords/);
    assert.match(edit, /KnowledgeResourceGrid/);
    assert.match(edit, /KnowledgeResourceRows/);
    assert.match(screen, /tr\('aiSetupSaveGreeting'\)/);
    assert.match(screen, /useKnowledgeMedia/);
    assert.match(screen, /multi\.save\(\{ dynamic_messages:/);
  });

  it('has ar/fr AI Basics keys', () => {
    const ar = read('i18n/locales/aiSetupAr.ts');
    const fr = read('i18n/locales/aiSetupFr.ts');
    for (const src of [ar, fr]) {
      assert.match(src, /aiSetupBasicsSubtitle:/);
      assert.match(src, /aiSetupBasicsStyleTab:/);
      assert.match(src, /aiSetupGreetingsSearch:/);
      assert.match(src, /aiSetupSaveChanges:/);
      assert.match(src, /aiSetupSaveGreeting:/);
      assert.match(src, /aiSetupGreetingActive:/);
    }
  });
});

/**
 * AI Setup restructure — hub cards, greeting rules, AI Basics composite.
 * Run: node --test mobile/linas-ai/tests/aiSetupRestructure.test.mjs
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

describe('AI Setup hub restructure', () => {
  it('hides languages and style from hub cards', () => {
    const src = read('features/cm/cmSections.ts');
    assert.match(src, /id: 'languages'[\s\S]*showInCmHub: false/);
    assert.match(src, /id: 'style'[\s\S]*showInCmHub: false/);
    assert.match(src, /CM_HUB_PROGRESS_EXCLUDED[\s\S]*languages[\s\S]*style/s);
    assert.doesNotMatch(src, /CM_HUB_CARDS[\s\S]*id: 'languages'/);
  });

  it('renames dynamic_messages hub card to Greetings', () => {
    const src = read('features/cm/cmSections.ts');
    assert.match(src, /id: 'dynamic_messages'[\s\S]*title: 'Greetings'/);
  });

  it('uses composite AI Basics editor with business name and style', () => {
    const basics = read('features/cm/editors/AiBasicsEditor.tsx');
    assert.match(basics, /clinic_name/);
    assert.match(basics, /assistant_name/);
    assert.match(basics, /AiBasicsStyleSection/);
    const screen = read('features/cm/CmSectionScreen.tsx');
    assert.match(screen, /useCmMultiDraft\(\['ai_basics', 'style'\]/);
  });

  it('greeting editor supports multiple rules with triggers', () => {
    const src = read('features/cm/editors/GreetingsEditor.tsx');
    assert.match(src, /trigger_mode/);
    assert.match(src, /trigger_pattern/);
    assert.match(src, /enabled/);
    assert.match(src, /aiSetupAddGreeting/);
  });

  it('excludes languages and style from hub progress summary', () => {
    const sections = read('features/cm/cmSections.ts');
    assert.match(sections, /CM_HUB_PROGRESS_EXCLUDED.*languages.*style/s);
    const hub = read('features/cm/cmHubProgress.ts');
    assert.match(hub, /CM_HUB_PROGRESS_EXCLUDED/);
    const screen = read('features/cm/CmScreen.tsx');
    assert.match(screen, /summarizeHubProgress/);
    assert.match(screen, /displaySummary\.percent/);
  });

  it('has i18n keys for new AI Setup strings in en/ar/fr', () => {
    for (const loc of ['aiSetupEn.ts', 'aiSetupAr.ts', 'aiSetupFr.ts']) {
      const src = read(`i18n/locales/${loc}`);
      assert.match(src, /aiSetupBusinessName/);
      assert.match(src, /aiSetupAddGreeting/);
      assert.match(src, /aiSetupStyleNote/);
      assert.match(src, /aiSetupLanguagesRemovedBody/);
    }
  });
});

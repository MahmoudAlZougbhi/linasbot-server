/**
 * AI Setup restructure — hub cards, greeting rules in AI Basics, Service hub tile.
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
  it('hides languages, style, greetings, and legacy services from hub cards', () => {
    const src = read('features/cm/cmSections.ts');
    assert.match(src, /id: 'languages'[\s\S]*showInCmHub: false/);
    assert.match(src, /id: 'style'[\s\S]*showInCmHub: false/);
    assert.match(src, /id: 'dynamic_messages'[\s\S]*showInCmHub: false/);
    assert.match(src, /id: 'services'[\s\S]*showInCmHub: false/);
    assert.match(src, /CM_HUB_PROGRESS_EXCLUDED[\s\S]*dynamic_messages[\s\S]*services/s);
    assert.doesNotMatch(src, /CM_HUB_CARDS[\s\S]*id: 'languages'/);
  });

  it('uses composite AI Basics editor with greetings and style', () => {
    const basics = read('features/cm/editors/AiBasicsEditor.tsx');
    assert.match(basics, /clinic_name/);
    assert.match(basics, /assistant_name/);
    assert.match(basics, /GreetingsEditor/);
    assert.match(basics, /AiBasicsStyleSection/);
    const screen = read('features/cm/CmSectionScreen.tsx');
    assert.match(screen, /useCmMultiDraft\(\['ai_basics', 'style', 'dynamic_messages'\]/);
  });

  it('greeting editor uses title and note only in the UI', () => {
    const src = read('features/cm/editors/GreetingsEditor.tsx');
    assert.match(src, /aiSetupAddGreetingRule/);
    assert.match(src, /aiSetupGreetingNote/);
    assert.doesNotMatch(src, /aiSetupGreetingTrigger/);
    assert.doesNotMatch(src, /chipRow/);
  });

  it('excludes hidden sections from hub progress summary', () => {
    const sections = read('features/cm/cmSections.ts');
    assert.match(sections, /CM_HUB_PROGRESS_EXCLUDED.*dynamic_messages.*services/s);
    const hub = read('features/cm/cmHubProgress.ts');
    assert.match(hub, /CM_HUB_PROGRESS_EXCLUDED/);
    const screen = read('features/cm/CmScreen.tsx');
    assert.match(screen, /summarizeHubProgress/);
    assert.match(screen, /displaySummary\.percent/);
  });

  it('lists Knowledge first and Service (prices) full-width in hub layout', () => {
    const sections = read('features/cm/cmSections.ts');
    const cardsBlock = sections.match(/export const CM_SECTION_CARDS[\s\S]*?\];/)?.[0] ?? '';
    const firstId = cardsBlock.match(/id: '([^']+)'/)?.[1];
    assert.equal(firstId, 'knowledge');
    assert.match(sections, /id: 'prices'[\s\S]*title: 'Service'/);

    const layout = read('features/cm/aiSetupHubLayout.ts');
    assert.match(layout, /AI_SETUP_FULL_WIDTH_IDS.*knowledge.*prices/s);
    assert.doesNotMatch(layout, /dynamic_messages/);

    const tree = read('app/AppScreenTree.tsx');
    assert.match(tree, /section === 'prices'/);
    assert.match(tree, /section === 'dynamic_messages'/);
  });

  it('has i18n keys for greetings and service UX in en/ar/fr', () => {
    for (const loc of ['aiSetupEn.ts', 'aiSetupAr.ts', 'aiSetupFr.ts']) {
      const src = read(`i18n/locales/${loc}`);
      assert.match(src, /aiSetupAddGreetingRule/);
      assert.match(src, /aiSetupGreetingNote/);
      assert.match(src, /aiSetupAddRequestRule/);
      assert.match(src, /aiSetupRequestNote/);
      assert.match(src, /servicesAddOption.*Add more option|Ajouter une option|إضافة خيار/);
      assert.match(src, /servicesTitle: 'Service'|servicesTitle: 'الخدمة'/);
    }
  });

  it('requests editor uses type title note only', () => {
    const src = read('features/cm/editors/RequestsAppointmentsEditor.tsx');
    assert.match(src, /aiSetupAddRequestRule/);
    assert.match(src, /aiSetupRequestNote/);
    assert.match(src, /aiSetupRequestTypeAppointment/);
    assert.doesNotMatch(src, /Seed common fields/);
    assert.doesNotMatch(src, /enabled_types/);
    assert.doesNotMatch(src, /module_enabled/);
  });
});

describe('Service option row UX', () => {
  it('groups option fields with price as the only labeled input', () => {
    const row = read('features/services/ServiceOptionRow.tsx');
    assert.match(row, /styles\.group/);
    assert.match(row, /label=\{tr\('servicesPrice'\)\}/);
    assert.doesNotMatch(row, /servicesMachineOptional/);
    assert.match(row, /servicesMachinePlaceholder/);
  });
});

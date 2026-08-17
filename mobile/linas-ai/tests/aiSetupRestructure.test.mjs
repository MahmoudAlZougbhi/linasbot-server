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
    assert.match(screen, /function AiBasicsSectionScreen/);
    assert.match(screen, /AI_BASICS_COMPOSITE_SECTIONS = \['ai_basics', 'style', 'dynamic_messages'\]/);
    assert.match(screen, /useCmMultiDraft\(AI_BASICS_COMPOSITE_SECTIONS/);
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

  it('lists Knowledge in catalog and Service (prices) in hub pair rows', () => {
    const sections = read('features/cm/cmSections.ts');
    const cardsBlock = sections.match(/export const CM_SECTION_CARDS[\s\S]*?\];/)?.[0] ?? '';
    const firstId = cardsBlock.match(/id: '([^']+)'/)?.[1];
    assert.equal(firstId, 'knowledge');
    assert.match(sections, /id: 'prices'[\s\S]*title: 'Services'/);
    assert.match(sections, /id: 'branches'[\s\S]*title: 'Locations & hours'/);
    const openingHoursCard = cardsBlock.match(/\{\s*id: 'opening_hours'[\s\S]*?\},/)?.[0] ?? '';
    assert.match(openingHoursCard, /title: 'Opening Hours'/);
    assert.match(openingHoursCard, /showInCmHub: false/);

    const layout = read('features/cm/aiSetupHubLayout.ts');
    assert.match(layout, /AI_SETUP_FULL_WIDTH_IDS.*ai_basics.*knowledge.*branches/s);
    assert.match(layout, /AI_SETUP_PAIR_ROWS[\s\S]*prices.*products/s);
    assert.match(layout, /AI_SETUP_PAIR_ROWS[\s\S]*comments.*requests_appointments/s);
    assert.doesNotMatch(layout, /opening_hours/);
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
      assert.match(src, /servicesAddPriceOption/);
      assert.match(src, /servicesTitle: 'Services'|servicesTitle: 'الخدمات'/);
    }
  });

  it('requests editor uses type title note only', () => {
    const src = read('features/cm/requestRules/RequestRuleEditView.tsx');
    assert.match(src, /aiSetupRequestTypeAppointment/);
    assert.match(src, /requestRulesNote/);
    assert.doesNotMatch(src, /Seed common fields/);
    assert.doesNotMatch(src, /enabled_types/);
    assert.doesNotMatch(src, /module_enabled/);
  });
});

describe('Services AI Setup screens', () => {
  it('lists, edits, and adds prices over the CM prices catalog', () => {
    const screen = read('features/services/ServicesScreen.tsx');
    const list = read('features/services/ServiceListView.tsx');
    const edit = read('features/services/ServiceEditView.tsx');
    const price = read('features/services/ServicePriceView.tsx');
    assert.match(screen, /useCmDraft\('prices'/);
    assert.match(list, /servicesSearch/);
    assert.match(list, /servicesFooter/);
    assert.match(edit, /servicesAddPriceOption/);
    assert.match(edit, /servicesMediaSection/);
    assert.match(price, /servicesSaveAndAddAnother|servicesAddDetail/);
    assert.match(price, /servicesPriceHelp/);
  });
});

/**
 * Knowledge list + edit screenshot handoff (no device required).
 * Run: node --test mobile/linas-ai/tests/knowledgeScreen.design.test.mjs
 */
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');
const src = (...p) => join(root, 'src', ...p);

function read(rel) {
  return readFileSync(src(...rel.split('/')), 'utf8');
}

describe('Knowledge screens match screenshot handoff', () => {
  it('list uses screenshot copy, search, count, cards, and published footer', () => {
    const list = read('features/cm/knowledge/KnowledgeListView.tsx');
    const card = read('features/cm/knowledge/KnowledgeCard.tsx');
    const screen = read('features/cm/knowledge/KnowledgeScreen.tsx');
    const en = read('i18n/locales/aiSetupEn.ts');

    assert.match(en, /knowledgeSubtitle: 'Teach Linas AI about your business'/);
    assert.match(en, /knowledgeAdd: '\+ Add knowledge'/);
    assert.match(en, /knowledgeSearch: 'Search knowledge'/);
    assert.match(en, /knowledgeFooter: 'Linas uses published knowledge when replying\.'/);
    assert.match(screen, /tr\('knowledgeSubtitle'\)/);
    assert.match(list, /tr\('knowledgeSearch'\)/);
    assert.match(list, /knowledgeCount/);
    assert.match(list, /AiSetupListHeader/);
    assert.match(list, /LinasSparkleIcon/);
    assert.match(list, /tr\('knowledgeFooter'\)/);
    assert.doesNotMatch(list, /PrimaryButton/);
    assert.match(card, /feather\('file-text'\)/);
    assert.match(card, /feather\('chevron-right'\)/);
    assert.match(card, /LOCATIONS_KNOWLEDGE_TITLE/);
    assert.match(screen, /onAdd=\{handleAdd\}/);
    assert.match(screen, /onOpenLocations/);
  });

  it('edit uses title, knowledge body, word count, info box, resources, delete, save', () => {
    const edit = read('features/cm/knowledge/KnowledgeEditView.tsx');
    const resources = read('features/cm/knowledge/KnowledgeResources.tsx');
    const screen = read('features/cm/knowledge/KnowledgeScreen.tsx');
    const en = read('i18n/locales/aiSetupEn.ts');

    assert.match(en, /knowledgeEditTitle: 'Edit knowledge'/);
    assert.match(en, /knowledgePublished: 'Published'/);
    assert.match(en, /knowledgeFieldBody: 'Knowledge'/);
    assert.match(
      en,
      /knowledgeInfoRecommended: 'Recommended: Around 1,000 words per note for clearer AI answers\.'/,
    );
    assert.match(en, /knowledgeInfoNotLimit: 'This is not a limit—you can write more\.'/);
    assert.match(
      en,
      /knowledgeInfoLanguage: 'You can write in any language\. English is recommended for the best results\.'/,
    );
    assert.match(en, /knowledgeResourcesHint: 'Add examples or files Linas can use when answering\.'/);
    assert.match(en, /knowledgeSave: 'Save changes'/);
    assert.match(en, /aiSetupSave: 'Save'/);
    assert.match(edit, /tr\('knowledgeEditTitle'\)/);
    assert.match(edit, /ClampedLongField/);
    assert.match(edit, /countWords/);
    assert.match(edit, /countLabel=\{wordLabel\}/);
    assert.match(edit, /tr\('knowledgeInfoRecommended'\)/);
    assert.match(resources, /knowledgeAddImage/);
    assert.match(resources, /knowledgeAddVideo/);
    assert.match(resources, /knowledgeAddFile/);
    assert.match(resources, /knowledgeAddLink/);
    assert.match(resources, /feather\('more-horizontal'\)/);
    assert.match(screen, /tr\('knowledgeDelete'\)/);
    assert.match(screen, /tr\('aiSetupSave'\)/);
    assert.match(screen, /feather\('trash-2'\)/);
  });

  it('wires Knowledge through CM section screen and locations navigation', () => {
    const section = read('features/cm/CmSectionScreen.tsx');
    const tree = read('app/AppScreenTree.tsx');
    assert.match(section, /KnowledgeScreen/);
    assert.match(section, /onOpenLocations/);
    assert.doesNotMatch(section, /case 'knowledge'/);
    assert.match(tree, /section: 'branches'/);
    assert.match(tree, /onOpenLocations/);
  });

  it('has ar/fr knowledge keys', () => {
    const ar = read('i18n/locales/aiSetupAr.ts');
    const fr = read('i18n/locales/aiSetupFr.ts');
    assert.match(ar, /knowledgeSubtitle: 'علّم Linas AI عن عملك'/);
    assert.match(fr, /knowledgeSubtitle: 'Apprenez à Linas AI à connaître votre entreprise'/);
    for (const srcText of [ar, fr]) {
      assert.match(srcText, /knowledgeAdd:/);
      assert.match(srcText, /knowledgeSave:/);
      assert.match(srcText, /aiSetupSave:/);
      assert.match(srcText, /knowledgeInfoRecommended:/);
    }
  });
});

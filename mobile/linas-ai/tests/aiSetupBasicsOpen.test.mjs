/**
 * AI Setup hub → AI Basics must open the composite editor (not remount-loop).
 * Run: node --test mobile/linas-ai/tests/aiSetupBasicsOpen.test.mjs
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

describe('AI Setup hub opens AI Basics', () => {
  it('hub tile id is ai_basics and press forwards that id', () => {
    const sections = read('features/cm/cmSections.ts');
    const hub = read('features/cm/AiSetupHubSections.tsx');
    const layout = read('features/cm/aiSetupHubLayout.ts');
    assert.match(sections, /id: 'ai_basics'/);
    assert.match(sections, /title: 'AI Basics'/);
    assert.match(layout, /AI_SETUP_FULL_WIDTH_IDS = \['ai_basics'/);
    assert.match(hub, /onPress=\{\(\) => onOpenSection\(tile\.id\)\}/);
  });

  it('AppScreenTree routes ai_basics to cm_section, not Services', () => {
    const tree = read('app/AppScreenTree.tsx');
    assert.match(tree, /onOpenSection=\{\(section\) => \{/);
    assert.match(tree, /section === 'prices'/);
    assert.match(tree, /section === 'dynamic_messages'/);
    assert.match(tree, /setScreen\(\{ name: 'cm_section', section, backTo: 'cm' \}\)/);
    assert.match(tree, /name === 'cm_section'[\s\S]*<EphemeralRoute>/);
    assert.match(tree, /<CmSectionScreen[\s\S]*section=\{screen\.section\}/);
    const pricesBlock = tree.match(/if \(section === 'prices'\)[\s\S]*?return;/)?.[0] ?? '';
    assert.doesNotMatch(pricesBlock, /ai_basics/);
  });

  it('CmSectionScreen mounts AiBasicsScreen before the standard draft screen', () => {
    const screen = read('features/cm/CmSectionScreen.tsx');
    const basics = read('features/cm/aiBasics/AiBasicsScreen.tsx');
    const hook = read('features/cm/useCmMultiDraft.ts');
    assert.match(screen, /AiBasicsScreen/);
    assert.match(
      screen,
      /if \(section === 'ai_basics' \|\| section === 'style' \|\| section === 'dynamic_messages'\)/,
    );
    assert.match(basics, /AI_BASICS_COMPOSITE_SECTIONS = \['ai_basics', 'style', 'dynamic_messages'\]/);
    assert.match(basics, /useCmMultiDraft\(AI_BASICS_COMPOSITE_SECTIONS/);
    assert.doesNotMatch(basics, /useCmMultiDraft\(\[/);
    assert.match(hook, /const sectionKey = sections\.join\(','\)/);
    assert.match(hook, /\[proposalReview, sectionKey\]/);
    const exported = screen.match(/export function CmSectionScreen[\s\S]*?\n\}/)?.[0] ?? '';
    assert.match(exported, /AiBasicsScreen/);
    assert.doesNotMatch(exported, /useCmDraft/);
    assert.doesNotMatch(exported, /useCmMultiDraft/);
  });
});

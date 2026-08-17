/**
 * Locations & hours screens match the design handoff and stay wired.
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

describe('Locations & hours design wiring', () => {
  it('uses a dedicated section screen for branches, not the generic save footer', () => {
    const screen = read('features/cm/CmSectionScreen.tsx');
    assert.match(screen, /LocationHoursSectionScreen/);
    assert.match(screen, /section === 'branches'/);
    assert.doesNotMatch(screen, /LocationOpeningHoursEditor/);
  });

  it('list, details, and hours screens include the screenshot controls', () => {
    const list = read('features/cm/editors/locationOpeningHours/BranchListView.tsx');
    const details = read('features/cm/editors/locationOpeningHours/BranchDetailsTab.tsx');
    const media = read('features/cm/editors/locationOpeningHours/BranchMediaSection.tsx');
    const hours = read('features/cm/editors/locationOpeningHours/BranchHoursTab.tsx');
    const edit = read('features/cm/editors/locationOpeningHours/BranchEditView.tsx');
    assert.match(list, /aiSetupLocSearch/);
    assert.match(list, /AiSetupListHeader/);
    assert.match(list, /LinasSparkleIcon/);
    assert.match(list, /aiSetupLocBanner/);
    assert.match(details, /aiSetupLocAddress/);
    assert.match(details, /external-link/);
    assert.match(media, /aiSetupLocMediaImage/);
    assert.match(media, /aiSetupLocMediaVideo/);
    assert.match(media, /pickVideoAttachment/);
    assert.match(media, /aiSetupLocMediaFile/);
    assert.match(media, /aiSetupLocMediaLink/);
    assert.match(hours, /aiSetupLocSetMultiple/);
    assert.match(hours, /aiSetupLocSaveHours/);
    assert.match(edit, /aiSetupLocSaveChanges/);
    assert.match(edit, /aiSetupLocDeleteBranch/);
    assert.match(edit, /aiSetupLocTabDetails/);
    assert.match(edit, /aiSetupLocTabHours/);
  });
});

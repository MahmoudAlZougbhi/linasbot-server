/**
 * Comments + Requests AI Setup screenshot handoff (no device required).
 * Run: node --test mobile/linas-ai/tests/commentsRequestsScreen.design.test.mjs
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

describe('Comments screens match screenshot handoff', () => {
  it('list uses sparkle, add, info, search, cards, and footer copy', () => {
    const list = read('features/cm/comments/CommentListView.tsx');
    const card = read('features/cm/comments/CommentCard.tsx');
    const en = read('i18n/locales/commentsSetupEn.ts');
    assert.match(en, /commentsSubtitle: 'Control how Linas responds to social comments\.'/);
    assert.match(en, /commentsAdd: 'Add comment rule'/);
    assert.match(en, /commentsInfoTitle: 'Rules are optional\.'/);
    assert.match(en, /Automatic is free and sends your exact message/);
    assert.match(en, /commentsSearch: 'Search comment rules'/);
    assert.match(en, /commentsFooter: 'Every rule uses the same comment icon\.'/);
    assert.match(list, /LinasSparkleIcon/);
    assert.match(list, /tr\('commentsAdd'\)/);
    assert.match(list, /tr\('commentsInfoTitle'\)/);
    assert.match(card, /feather\('message-circle'\)/);
    assert.match(card, /commentsActive/);
  });

  it('edit covers automatic, AI reply, resources, delete, and save', () => {
    const edit = read('features/cm/comments/CommentEditView.tsx');
    const resources = read('features/cm/comments/CommentResources.tsx');
    const screen = read('features/cm/comments/CommentsScreen.tsx');
    const en = read('i18n/locales/commentsSetupEn.ts');
    assert.match(en, /commentsEditAi: 'Edit AI reply'/);
    assert.match(en, /commentsEditAutomatic: 'Edit automatic reply'/);
    assert.match(en, /commentsNote: 'Note for Linas'/);
    assert.match(en, /commentsResourcesAutoHint: 'For a public comment: Image or Link/);
    assert.match(edit, /commentsTypeAutomatic/);
    assert.match(edit, /commentsChoosePosts/);
    assert.match(edit, /commentsReplyBoth/);
    assert.match(resources, /commentsAddImage/);
    assert.match(resources, /feather\('more-horizontal'\)/);
    assert.match(screen, /tr\('commentsDelete'\)/);
    assert.match(screen, /tr\('commentsSave'\)/);
    assert.match(screen, /useCmDraft\('comments'/);
  });

  it('choose posts loads Graph posts and keeps manual post IDs', () => {
    const posts = read('features/cm/comments/CommentPostsView.tsx');
    const api = read('features/cm/comments/commentPostsApi.ts');
    const screen = read('features/cm/comments/CommentsScreen.tsx');
    assert.match(posts, /commentsChooseTitle/);
    assert.match(posts, /commentsPreviewPost/);
    assert.match(posts, /commentsUseSelected/);
    assert.match(posts, /commentsManualPostId/);
    assert.match(api, /\/api\/cm\/comment-rules\/posts/);
    assert.match(api, /\/api\/cm\/comment-rules\/accounts/);
    assert.match(screen, /allowManual/);
    assert.match(screen, /commentsGraphDenied/);
  });
});

describe('Requests screens match screenshot handoff', () => {
  it('list uses sparkle, add, info, search, clipboard cards, published footer', () => {
    const list = read('features/cm/requestRules/RequestRuleListView.tsx');
    const card = read('features/cm/requestRules/RequestRuleCard.tsx');
    const en = read('i18n/locales/requestSetupEn.ts');
    assert.match(en, /requestRulesSubtitle: 'Rules for appointments, orders, and other customer requests\.'/);
    assert.match(en, /requestRulesAdd: 'Add request rule'/);
    assert.match(en, /requestRulesInfoTitle: 'What is a request rule\?'/);
    assert.match(en, /requestRulesSearch: 'Search request rules'/);
    assert.match(en, /requestRulesFooter: 'Every rule uses the same request icon\.'/);
    assert.match(list, /LinasSparkleIcon/);
    assert.match(card, /clipboard-text-outline/);
    assert.match(card, /requestRulesPublished/);
    assert.match(card, /requestRulesCollects/);
  });

  it('edit saves CM draft and publishes existing request graphs', () => {
    const edit = read('features/cm/requestRules/RequestRuleEditView.tsx');
    const screen = read('features/cm/requestRules/RequestRulesScreen.tsx');
    const api = read('features/cm/requestRules/requestGraphsApi.ts');
    assert.match(edit, /requestRulesEditTitle/);
    assert.match(edit, /aiSetupRequestTypeAppointment/);
    assert.match(screen, /useCmDraft\('requests_appointments'/);
    assert.match(screen, /publishRequestGraph/);
    assert.match(screen, /listRequestGraphs/);
    assert.match(api, /\/api\/cm\/request-graphs\/publish/);
    assert.doesNotMatch(screen, /enabled_types/);
  });

  it('wires Comments and Requests through CM section screen', () => {
    const section = read('features/cm/CmSectionScreen.tsx');
    assert.match(section, /CommentsScreen/);
    assert.match(section, /RequestRulesScreen/);
    assert.doesNotMatch(section, /CommentsEditor/);
    assert.doesNotMatch(section, /RequestsAppointmentsEditor/);
  });

  it('has ar/fr keys', () => {
    for (const loc of ['commentsSetupAr.ts', 'commentsSetupFr.ts', 'requestSetupAr.ts', 'requestSetupFr.ts']) {
      const srcText = read(`i18n/locales/${loc}`);
      assert.match(srcText, /Subtitle:/);
    }
  });
});

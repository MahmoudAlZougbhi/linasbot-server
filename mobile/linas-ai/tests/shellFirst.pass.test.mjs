/**
 * Shell-first / SWR / persist contracts (no device required).
 */
import assert from 'node:assert/strict';
import { describe, it } from 'node:test';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { KEEP_MOUNTED_LIMIT, KEEP_MOUNTED_SCREENS } from '../src/app/keepMountedPolicy.ts';
import {
  isPersistableQueryKey,
  mergePersistSnapshots,
  QUERY_PERSIST_NEEDLES,
} from '../src/cache/queryPersistLogic.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

const MODULE_SURFACES = [
  'features/dashboard/DashboardScreen.tsx',
  'features/livechat/LiveChatInbox.tsx',
  'features/cm/CmScreen.tsx',
  'features/products/ProductsScreen.tsx',
  'features/services/ServicesScreen.tsx',
  'features/integrations/IntegrationsScreen.tsx',
  'features/requests/RequestsHome.tsx',
  'features/users/UsersScreen.tsx',
  'features/billing/BillingScreen.tsx',
  'features/notifications/NotificationsScreen.tsx',
  'features/faq/FaqScreen.tsx',
  'features/smartFollowUp/SmartFollowUpScreen.tsx',
];

describe('shell-first screens', () => {
  it('ScreenSkeleton covers list/inbox/cards/form/chart layouts', () => {
    const skeleton = read('components/ScreenSkeleton.tsx');
    assert.match(skeleton, /variant === 'inbox'/);
    assert.match(skeleton, /variant === 'cards'/);
    assert.match(skeleton, /variant === 'form'/);
    assert.match(skeleton, /variant === 'chart'/);
    assert.match(skeleton, /accessibilityRole="progressbar"/);
    assert.match(skeleton, /useReduceMotion/);
  });

  it('chrome renders before API: ScreenChrome stays outside the body gate', () => {
    for (const rel of MODULE_SURFACES) {
      const source = read(rel);
      assert.match(source, /ScreenChrome|InboxSearchBar|RequestSearchBar|RequestSummaryCards/, `${rel} must paint chrome`);
      const chromeIdx = source.search(/<ScreenChrome|<InboxSearchBar|<RequestSearchBar|<RequestSummaryCards/);
      const skeletonIdx = source.search(/<ScreenSkeleton/);
      assert.ok(chromeIdx >= 0 && skeletonIdx > chromeIdx, `${rel} paints chrome before skeleton`);
      assert.doesNotMatch(source, /variant="screen"/, `${rel} must not use a full-screen spinner`);
    }
  });

  it('cold products/services/cm drafts show skeleton, not a screen spinner', () => {
    assert.match(read('features/products/ProductsScreen.tsx'), /ScreenSkeleton variant="list"/);
    assert.match(read('features/products/ProductsScreen.tsx'), /if \(!hit && !cached\) setLoading\(true\)/);
    assert.match(read('features/services/ServicesScreen.tsx'), /draft\.loading \? <ScreenSkeleton/);
    assert.match(read('features/cm/useCmDraft.ts'), /useState\(!cached\)/);
    assert.doesNotMatch(read('features/products/ProductsScreen.tsx'), /variant="screen"/);
    assert.doesNotMatch(read('features/services/ServicesScreen.tsx'), /variant="screen"/);
  });

  it('cached dashboard/products/billing paint without loading=true', () => {
    assert.match(read('features/dashboard/useTenantDashboard.ts'), /seeded\s*\n\s*\? \{/);
    assert.match(read('features/dashboard/useTenantDashboard.ts'), /kind: 'ready'/);
    assert.match(read('features/products/ProductsScreen.tsx'), /useState\(!cached\)/);
    assert.match(read('features/products/ProductsScreen.tsx'), /useState\(Boolean\(cached\)\)/);
    const billing = read('features/billing/useBillingData.ts');
    assert.match(billing, /queryKeys\.billing\(\)/);
    assert.match(billing, /seedBillingState/);
    assert.match(billing, /loading: cacheGet\(queryKeys\.billing\(\)\) == null/);
    assert.match(billing, /if \(painted\) \{/);
    assert.match(billing, /persistBilling\(next\)/);
  });

  it('failed refresh keeps cached requests/products/live chat rows', () => {
    const req = read('features/requests/RequestsHome.tsx');
    assert.match(req, /list\.error && list\.items\.length > 0/);
    assert.match(req, /list\.errorKind === 'offline' && list\.items\.length === 0 && list\.hasLoadedOnce/);
    assert.match(read('features/products/ProductsScreen.tsx'), /setError\(tr\('productsLoadError'\)\)/);
    assert.match(read('features/livechat/useLiveChatInbox.ts'), /Keep existing list/);
    assert.match(read('features/dashboard/useTenantDashboard.ts'), /refreshError: message/);
  });

  it('empty list after load is EmptyState, not leftover skeleton', () => {
    assert.match(read('features/livechat/LiveChatInbox.tsx'), /cold \? \([\s\S]*ScreenSkeleton[\s\S]*EmptyState/);
    assert.match(read('features/requests/RequestsHome.tsx'), /cold \? <ScreenSkeleton[\s\S]*EmptyState/);
    assert.match(read('features/products/ProductListView.tsx'), /productsEmpty/);
  });
});

describe('cache persist + isolation', () => {
  it('logout clears RAM cache and disk snapshots', () => {
    const bind = read('cache/bindSessionCaches.ts');
    assert.match(bind, /cacheClear\(\)/);
    assert.match(bind, /clearQueryPersist/);
    assert.match(bind, /clearCmDraftCache/);
    assert.match(read('auth/restoreOwnerSession.ts'), /hydrateQueryPersist/);
  });

  it('persist keys are tenant-scoped and skip threads/tokens', () => {
    assert.ok(QUERY_PERSIST_NEEDLES.includes('|livechat|inbox|'));
    assert.ok(isPersistableQueryKey('linas:u1|livechat|inbox|all|all|'));
    assert.ok(isPersistableQueryKey('linas:u1|products'));
    assert.equal(isPersistableQueryKey('linas:u1|livechat|thread|abc'), false);
    assert.equal(isPersistableQueryKey('access_token'), false);
    assert.match(read('cache/queryPersist.ts'), /sessionScopeId\(\)/);
    assert.match(read('cache/sessionScope.ts'), /tenant:\$\{user\.id\}|`\$\{tenant\}:\$\{user\.id\}`/);
  });

  it('disk flush merges snapshots and drops disallowed keys', () => {
    const merged = mergePersistSnapshots(
      { 't:u|dashboard|all|UTC': { data: { a: 1 }, updatedAt: 1 } },
      {
        't:u|products': { data: [2], updatedAt: 2 },
        't:u|livechat|thread|x': { data: { secret: true }, updatedAt: 3 },
      },
    );
    assert.equal(merged['t:u|dashboard|all|UTC'].data.a, 1);
    assert.deepEqual(merged['t:u|products'].data, [2]);
    assert.equal(merged['t:u|livechat|thread|x'], undefined);
  });
});

describe('prefetch + keep-mounted + navigation', () => {
  it('idle prefetch is sequential, abortable, and skips fresh keys', () => {
    const prefetch = read('cache/idlePrefetch.ts');
    assert.match(prefetch, /for \(const job of jobs\)/);
    assert.match(prefetch, /if \(signal\.aborted\) return/);
    assert.match(prefetch, /isCacheFresh/);
    assert.match(prefetch, /prefetchProducts/);
    assert.match(prefetch, /InteractionManager\.runAfterInteractions/);
    assert.match(read('app/AppShell.tsx'), /scheduleIdlePrefetch\(ac\.signal\)/);
    assert.match(read('app/AppShell.tsx'), /ac\.abort\(\)/);
    assert.match(read('app/AppShell.tsx'), /hasAccess, authEpoch/);
  });

  it('Products/Services reopen from cache, not keep-mounted', () => {
    assert.deepEqual([...KEEP_MOUNTED_SCREENS], ['chat', 'livechat', 'dashboard', 'cm']);
    assert.equal(KEEP_MOUNTED_LIMIT, 4);
    const tree = read('app/AppScreenTree.tsx');
    assert.match(tree, /name === 'products'[\s\S]*<EphemeralRoute>/);
    assert.match(tree, /name === 'services'[\s\S]*<EphemeralRoute>/);
    assert.doesNotMatch(read('app/keepMountedPolicy.ts'), /'products'/);
    assert.doesNotMatch(read('app/keepMountedPolicy.ts'), /'services'/);
    assert.match(read('app/ModulePane.tsx'), /if \(!active\) return null/);
  });

  it('navigation setScreen is local and not awaited on a fetch', () => {
    const shell = read('app/AppShell.tsx');
    assert.match(shell, /setScreen\(\{/);
    assert.doesNotMatch(shell, /await[\s\S]{0,40}setScreen/);
    const nav = read('app/moduleNav.ts');
    assert.match(nav, /openArea/);
    assert.doesNotMatch(nav, /await apiFetch/);
  });

  it('focus refetch skips fresh TTL; pull-to-refresh forces', () => {
    assert.match(read('features/requests/useRequestsList.ts'), /refresh: \(opts\?: \{ force\?: boolean \}\)/);
    assert.match(read('features/requests/RequestsHome.tsx'), /list\.refresh\(\{ force: true \}\)/);
    assert.match(read('features/livechat/useLiveChatInbox.ts'), /catchUpIfStale/);
    assert.match(read('features/integrations/useIntegrationsLoad.ts'), /if \(!opts\?\.force && hit && isCacheFresh/);
    assert.match(read('features/dashboard/useTenantDashboard.ts'), /refreshIfStale: \(\) => load\(\{ soft: true \}\)/);
  });
});

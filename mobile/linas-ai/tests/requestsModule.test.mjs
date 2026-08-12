import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('Requests mobile module', () => {
  it('wires requests through control area, drawer, icons, nav, and screen tree', () => {
    assert.match(read('features/control/controlAreas.ts'), /'requests'/);
    assert.match(read('features/nav/drawerModules.ts'), /id:\s*'requests'/);
    assert.match(read('features/nav/moduleIcons.ts'), /requests:\s*feather\('clipboard'\)/);
    assert.match(read('app/navigation.ts'), /name:\s*'requests'/);
    assert.match(read('app/AppShell.tsx'), /area === 'requests'/);
    assert.match(read('app/moduleNav.ts'), /case 'requests'/);
    const tree = read('app/AppScreenTree.tsx');
    assert.match(tree, /RequestsScreen/);
    assert.ok(
      tree.includes("KeepMountedPane key={`requests-${authEpoch}`}"),
      'missing keep-mounted pane for requests',
    );
  });

  it('API client hits /api/requests* endpoints without mock success', () => {
    const api = read('features/requests/requestsApi.ts');
    assert.match(api, /\/api\/requests\/setup-status/);
    assert.match(api, /\/api\/requests\?/);
    assert.match(api, /\/api\/requests\/\$\{encodeURIComponent\(requestId\)\}/);
    assert.match(api, /\/assign/);
    assert.match(api, /\/notes/);
    assert.match(api, /\/final-action/);
    assert.match(api, /\/notify-retry/);
    assert.doesNotMatch(api, /mockSuccess|fakeSuccess|SecureStore/);
  });

  it('cards omit full phone and address fields', () => {
    const card = read('features/requests/RequestCardRow.tsx');
    assert.doesNotMatch(card, /phone_normalized|delivery_address/);
    assert.match(card, /reqNotifyFailed/);
    const types = read('features/requests/requestsTypes.ts');
    assert.match(types, /function cardSummary/);
  });

  it('detail supports chat link, final actions, notes, and notify retry', () => {
    const detail = read('features/requests/RequestDetailView.tsx');
    assert.match(detail, /reqChatCustomer/);
    assert.match(detail, /onOpenLiveChat/);
    assert.match(detail, /runFinalAction/);
    assert.match(detail, /retryRequestNotify/);
    assert.match(detail, /addRequestNote/);
    assert.match(detail, /RequestFinalActionModal/);
  });

  it('home covers counters, filters, setup-required, and pagination hooks', () => {
    const home = read('features/requests/RequestsHome.tsx');
    assert.match(home, /COUNTER_STATUSES/);
    assert.match(home, /reqSetupRequiredTitle/);
    assert.match(home, /onEndReached/);
    assert.match(home, /RefreshControl/);
    const hook = read('features/requests/useRequestsList.ts');
    assert.match(hook, /fetchRequestsSetupStatus/);
    assert.match(hook, /listRequests/);
    assert.match(hook, /withinDatePreset/);
  });

  it('permission labels include requests keys', () => {
    const modal = read('features/users/UserFormModal.tsx');
    assert.match(modal, /requests:\s*'permRequests'/);
    assert.match(modal, /requestsSensitive:\s*'permRequestsSensitive'/);
    const perms = read('features/users/usersPermissions.ts');
    assert.match(perms, /'requests'/);
    assert.match(perms, /'requestsManage'/);
  });
});

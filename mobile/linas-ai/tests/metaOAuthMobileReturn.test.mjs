import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import { metaAuthSessionOutcome } from '../src/app/integrationsDeepLink.ts';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('meta oauth mobile return surface', () => {
  it('starts OAuth with return_surface=mobile', () => {
    const oauth = read('features/integrations/integrationsOAuth.ts');
    assert.match(oauth, /return_surface:\s*MOBILE_RETURN_SURFACE|return_surface:\s*'mobile'/);
  });

  it('opens Meta OAuth in an in-app auth session, not the Instagram app', () => {
    const oauth = read('features/integrations/integrationsOAuth.ts');
    const screen = read('features/integrations/IntegrationsScreen.tsx');
    assert.match(oauth, /openAuthSessionAsync/);
    assert.match(oauth, /withInstagramMobileReauth/);
    assert.match(oauth, /force_reauth/);
    assert.match(oauth, /MetaOAuthConnectError/);
    assert.match(oauth, /metaAuthSessionOutcome/);
    assert.match(screen, /MetaOAuthConnectError/);
    assert.match(screen, /metaOAuthCancelled/);
    assert.match(screen, /metaOAuthIncomplete/);
    assert.match(screen, /apiErrorDetail/);
  });

  it('does not treat Facebook HTTPS session success as connected', () => {
    assert.equal(
      metaAuthSessionOutcome({
        type: 'success',
        url: 'https://www.facebook.com/v22.0/dialog/oauth?redirect_uri=https://www.linasaibot.com/oauth/meta/callback',
      }),
      'incomplete',
    );
    assert.equal(
      metaAuthSessionOutcome({
        type: 'success',
        url: 'https://www.linasaibot.com/oauth/meta/callback?code=abc',
      }),
      'incomplete',
    );
    assert.equal(
      metaAuthSessionOutcome({
        type: 'success',
        url: 'linasai://integrations?meta_connection=success',
      }),
      'ok',
    );
    assert.equal(metaAuthSessionOutcome({ type: 'dismiss' }), 'cancelled');
    assert.equal(metaAuthSessionOutcome({ type: 'cancel' }), 'cancelled');
    assert.equal(
      metaAuthSessionOutcome({
        type: 'success',
        url: 'linasai://integrations?meta_connection=failed',
      }),
      'failed',
    );
  });

  it('refetches integrations after Meta OAuth and trusts the connected row', () => {
    const screen = read('features/integrations/IntegrationsScreen.tsx');
    const load = read('features/integrations/useIntegrationsLoad.ts');
    assert.match(screen, /const session = await startMetaOAuth\(platform\)/);
    assert.match(screen, /await load\(\)/);
    assert.match(screen, /row\?\.connected/);
    assert.match(screen, /metaOAuthSuccess/);
    assert.match(load, /return \{ ok: true, rows: data\.integrations \}/);
  });

  it('parses integrations deep link without tokens', () => {
    const nav = read('app/navigation.ts');
    const link = read('app/integrationsDeepLink.ts');
    assert.match(nav, /parseIntegrationsDeepLink/);
    assert.match(link, /meta_connection/);
    assert.doesNotMatch(link, /access_token|tenant_id/);
  });

  it('AppShell routes integrations deep link and IntegrationsScreen refetches', () => {
    const shell = read('app/AppShell.tsx');
    const screen = read('features/integrations/IntegrationsScreen.tsx');
    const load = read('features/integrations/useIntegrationsLoad.ts');
    assert.match(shell, /parseIntegrationsDeepLink/);
    assert.match(shell, /setScreen\(\{\s*name:\s*'integrations'/);
    assert.match(screen, /useIntegrationsLoad/);
    assert.match(load, /AppState\.addEventListener/);
    assert.match(load, /parseIntegrationsDeepLink/);
    assert.match(load, /Linking\.addEventListener/);
  });
});

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  metaAuthSessionOutcome,
  metaOAuthFailureMessage,
  parseIntegrationsDeepLink,
} from '../src/app/integrationsDeepLink.ts';

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
    const connect = read('features/integrations/useMetaPlatformConnect.ts');
    assert.match(oauth, /openAuthSessionAsync/);
    assert.match(oauth, /withInstagramMobileReauth/);
    assert.match(oauth, /force_reauth/);
    assert.match(oauth, /MetaOAuthConnectError/);
    assert.match(oauth, /metaAuthSessionOutcome/);
    assert.match(connect, /MetaOAuthConnectError/);
    assert.match(connect, /metaOAuthCancelled/);
    assert.match(connect, /metaOAuthIncomplete/);
    assert.match(connect, /apiErrorDetail/);
  });

  it('does not treat Facebook HTTPS session success as connected', () => {
    assert.deepEqual(
      metaAuthSessionOutcome({
        type: 'success',
        url: 'https://www.facebook.com/v22.0/dialog/oauth?redirect_uri=https://www.linasaibot.com/oauth/meta/callback',
      }),
      { outcome: 'incomplete', reason: null },
    );
    assert.deepEqual(
      metaAuthSessionOutcome({
        type: 'success',
        url: 'https://www.linasaibot.com/oauth/meta/callback?code=abc',
      }),
      { outcome: 'incomplete', reason: null },
    );
    assert.deepEqual(
      metaAuthSessionOutcome({
        type: 'success',
        url: 'linasai://integrations?meta_connection=success',
      }),
      { outcome: 'ok', reason: null },
    );
    assert.deepEqual(metaAuthSessionOutcome({ type: 'dismiss' }), {
      outcome: 'cancelled',
      reason: null,
    });
    assert.deepEqual(metaAuthSessionOutcome({ type: 'cancel' }), {
      outcome: 'cancelled',
      reason: null,
    });
    assert.deepEqual(
      metaAuthSessionOutcome({
        type: 'success',
        url: 'linasai://integrations?meta_connection=failed&meta_reason=token',
      }),
      { outcome: 'failed', reason: 'token' },
    );
  });

  it('refetches integrations after Meta OAuth and trusts the connected row', () => {
    const screen = read('features/integrations/IntegrationsScreen.tsx');
    const connect = read('features/integrations/useMetaPlatformConnect.ts');
    const load = read('features/integrations/useIntegrationsLoad.ts');
    assert.match(screen, /useMetaPlatformConnect/);
    assert.match(connect, /const session = await startMetaOAuth\(platform\)/);
    assert.match(connect, /await load\(\)/);
    assert.match(connect, /row\?\.connected/);
    assert.match(connect, /metaOAuthSuccess/);
    assert.match(load, /return \{ ok: true, rows: data\.integrations \}/);
  });

  it('parses integrations deep link without tokens', () => {
    const nav = read('app/navigation.ts');
    const link = read('app/integrationsDeepLink.ts');
    assert.match(nav, /parseIntegrationsDeepLink/);
    assert.match(link, /meta_connection/);
    assert.doesNotMatch(link, /access_token|tenant_id/);
  });

  it('keeps Facebook and Instagram OAuth failures channel-specific', () => {
    const facebook = parseIntegrationsDeepLink(
      'linasai://integrations?meta_connection=failed&meta_reason=scopes&channel=facebook',
    );
    const instagram = parseIntegrationsDeepLink(
      'linasai://integrations?meta_connection=failed&meta_reason=scopes&channel=instagram',
    );
    const tr = (key) => key;

    assert.equal(facebook?.metaChannel, 'facebook');
    assert.equal(instagram?.metaChannel, 'instagram');
    assert.equal(
      metaOAuthFailureMessage(tr, facebook?.metaReason ?? null, facebook?.metaChannel ?? null),
      'metaOAuthFailedFacebookScopes',
    );
    assert.equal(
      metaOAuthFailureMessage(tr, instagram?.metaReason ?? null, instagram?.metaChannel ?? null),
      'metaOAuthFailedScopes',
    );
    assert.equal(
      metaOAuthFailureMessage(tr, 'busy', 'facebook'),
      'metaOAuthFailedFacebookBusy',
    );
    assert.equal(
      metaOAuthFailureMessage(tr, 'guard', 'instagram'),
      'metaOAuthFailedGuard',
    );
    assert.equal(
      metaOAuthFailureMessage(tr, 'deletion_failed', 'facebook'),
      'metaOAuthFailedFacebookDeletionFailed',
    );
    assert.equal(
      metaOAuthFailureMessage(tr, 'deletion_failed', 'instagram'),
      'metaOAuthFailedDeletionFailed',
    );
    const invalidChannel = parseIntegrationsDeepLink(
      'linasai://integrations?meta_connection=failed&meta_reason=scopes&channel=whatsapp',
    );
    assert.equal(invalidChannel?.metaChannel, null);
    assert.equal(
      metaOAuthFailureMessage(
        tr,
        invalidChannel?.metaReason ?? null,
        invalidChannel?.metaChannel ?? null,
      ),
      'metaOAuthFailed',
    );
    assert.equal(metaOAuthFailureMessage(tr, 'scopes', null), 'metaOAuthFailed');
  });

  it('Facebook scopes copy covers Page grants, not only business_management', () => {
    const en = read('i18n/locales/integrationsDisplayEn.ts');
    const ar = read('i18n/locales/integrationsDisplayAr.ts');
    const fr = read('i18n/locales/integrationsDisplayFr.ts');
    assert.match(en, /Facebook did not grant all required permissions, including business_management/);
    assert.match(ar, /كل الصلاحيات المطلوبة، بما فيها business_management/);
    assert.match(fr, /toutes les autorisations requises, y compris business_management/);
    assert.doesNotMatch(en, /the required business_management permission/);
    assert.doesNotMatch(ar, /صلاحية business_management المطلوبة/);
    assert.doesNotMatch(fr, /l’autorisation business_management requise/);
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

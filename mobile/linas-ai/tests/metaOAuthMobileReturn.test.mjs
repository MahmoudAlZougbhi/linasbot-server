import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

import {
  metaAuthSessionOutcome,
  metaOAuthFailureMessage,
  metaOAuthFailureReasonFromApiBody,
  parseIntegrationsDeepLink,
} from '../src/app/integrationsDeepLink.ts';
import {
  errorAfterIntegrationLoadFailure,
  errorAfterIntegrationLoadSuccess,
  shouldApplyMetaSessionFeedback,
} from '../src/features/integrations/integrationsFeedback.ts';
import { ar } from '../src/i18n/locales/ar.ts';
import { en } from '../src/i18n/locales/en.ts';
import { fr } from '../src/i18n/locales/fr.ts';
import { integrationsDisplayAr } from '../src/i18n/locales/integrationsDisplayAr.ts';
import { integrationsDisplayEn } from '../src/i18n/locales/integrationsDisplayEn.ts';
import { integrationsDisplayFr } from '../src/i18n/locales/integrationsDisplayFr.ts';

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
    assert.doesNotMatch(connect, /apiErrorDetail/);
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
    assert.equal(
      metaOAuthFailureMessage(tr, 'no_page', 'facebook'),
      'metaOAuthFailedFacebookNoPage',
    );
    assert.equal(
      metaOAuthFailureMessage(tr, 'provider', 'instagram'),
      'metaOAuthFailedProvider',
    );
    assert.equal(
      metaOAuthFailureMessage(tr, 'rate_limit', 'instagram'),
      'metaOAuthFailedRateLimit',
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

  it('allowlists only safe no-page/provider reason codes', () => {
    assert.equal(
      parseIntegrationsDeepLink(
        'linasai://integrations?meta_connection=failed&meta_reason=no_page&channel=facebook',
      )?.metaReason,
      'no_page',
    );
    assert.equal(
      parseIntegrationsDeepLink(
        'linasai://integrations?meta_connection=failed&meta_reason=provider&channel=instagram',
      )?.metaReason,
      'provider',
    );
    assert.equal(
      parseIntegrationsDeepLink(
        'linasai://integrations?meta_connection=failed&meta_reason=rate_limit&channel=instagram',
      )?.metaReason,
      'rate_limit',
    );
    assert.equal(
      parseIntegrationsDeepLink(
        'linasai://integrations?meta_connection=failed&meta_reason=raw_provider_exception&channel=instagram',
      )?.metaReason,
      null,
    );
  });

  it('Facebook scopes message covers all required permissions, including business_management', () => {
    for (const locale of [integrationsDisplayEn, integrationsDisplayAr, integrationsDisplayFr]) {
      const tr = (key) => {
        const value = locale[key];
        assert.equal(typeof value, 'string', `missing Facebook scopes copy for ${key}`);
        return value;
      };
      const message = metaOAuthFailureMessage(tr, 'scopes', 'facebook');
      assert.match(message, /business_management/);
      assert.match(
        message,
        /all required permissions|كل الصلاحيات المطلوبة|toutes les autorisations requises/,
      );
      assert.doesNotMatch(message, /the required business_management permission/);
      assert.doesNotMatch(message, /صلاحية business_management المطلوبة/);
      assert.doesNotMatch(message, /l’autorisation business_management requise/);
      assert.doesNotMatch(message, /select the Business|اختر الـ Business|sélectionnez l’entreprise/i);
    }
  });

  it('gives actionable no-page/provider copy in every supported locale', () => {
    const localeCases = [
      {
        locale: integrationsDisplayEn,
        noPage: /full control/i,
        provider: /after two checks/i,
        rateLimit: /graph error 613/i,
      },
      {
        locale: integrationsDisplayAr,
        noPage: /تحكماً كاملاً/,
        provider: /بعد محاولتين/,
        rateLimit: /Graph 613/,
      },
      {
        locale: integrationsDisplayFr,
        noPage: /contrôle total/i,
        provider: /après deux vérifications/i,
        rateLimit: /erreur Graph 613/i,
      },
    ];
    for (const { locale, noPage, provider, rateLimit } of localeCases) {
      assert.match(locale.metaOAuthFailedFacebookNoPage, noPage);
      assert.match(locale.metaOAuthFailedProvider, provider);
      assert.match(locale.metaOAuthFailedRateLimit, rateLimit);
      assert.doesNotMatch(locale.metaOAuthFailedProvider, /five minutes|cinq minutes|خمس دقائق/i);
      assert.doesNotMatch(locale.metaOAuthFailedRateLimit, /five minutes|cinq minutes|خمس دقائق/i);
    }
  });

  it('never tells a disconnected channel to Disconnect after a generic OAuth failure', () => {
    for (const message of [
      integrationsDisplayEn.metaOAuthFailedFacebook,
      integrationsDisplayAr.metaOAuthFailedFacebook,
      integrationsDisplayFr.metaOAuthFailedFacebook,
      en.metaOAuthFailed,
      ar.metaOAuthFailed,
      fr.metaOAuthFailed,
    ]) {
      assert.doesNotMatch(message, /disconnect|افصل|déconnect/i);
    }
  });

  it('does not expose raw API error detail in Meta Connect feedback', () => {
    const oauth = read('features/integrations/integrationsOAuth.ts');
    const connect = read('features/integrations/useMetaPlatformConnect.ts');
    assert.doesNotMatch(oauth, /apiErrorDetail/);
    assert.doesNotMatch(connect, /apiErrorDetail|err\.message|String\(err\.body\)/);
    assert.match(connect, /metaOAuthFailureReasonFromApiBody\(err\.body\)/);
    assert.match(connect, /err instanceof ApiError[\s\S]*tr\('integrationsActionError'\)/);
    assert.equal(
      metaOAuthFailureReasonFromApiBody({ detail: { meta_reason: 'provider' } }),
      'provider',
    );
    assert.equal(
      metaOAuthFailureReasonFromApiBody({ detail: { meta_reason: 'no_page' } }),
      'no_page',
    );
    assert.equal(
      metaOAuthFailureReasonFromApiBody({ detail: { meta_reason: 'raw_provider_exception' } }),
      null,
    );
    assert.equal(
      metaOAuthFailureReasonFromApiBody({ detail: 'Instagram provider token=secret' }),
      null,
    );
  });

  it('keeps specific OAuth feedback across refresh and rejects a stale session fallback', () => {
    assert.equal(
      errorAfterIntegrationLoadSuccess('facebook-no-page', 'integrations-load-error'),
      'facebook-no-page',
    );
    assert.equal(
      errorAfterIntegrationLoadSuccess('integrations-load-error', 'integrations-load-error'),
      null,
    );
    assert.equal(
      errorAfterIntegrationLoadFailure('instagram-provider', 'integrations-load-error'),
      'instagram-provider',
    );
    assert.equal(errorAfterIntegrationLoadFailure(null, 'integrations-load-error'), 'integrations-load-error');
    assert.equal(shouldApplyMetaSessionFeedback(4, 4), true);
    assert.equal(shouldApplyMetaSessionFeedback(4, 5), false);

    const load = read('features/integrations/useIntegrationsLoad.ts');
    const connect = read('features/integrations/useMetaPlatformConnect.ts');
    assert.match(load, /metaResultSequence\.current \+= 1/);
    assert.match(load, /errorAfterIntegrationLoadSuccess/);
    assert.match(load, /errorAfterIntegrationLoadFailure/);
    assert.match(connect, /shouldApplyMetaSessionFeedback/);
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

import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it } from 'node:test';

const root = join(dirname(fileURLToPath(import.meta.url)), '..');

function read(rel) {
  return readFileSync(join(root, 'src', rel), 'utf8');
}

describe('meta oauth mobile return surface', () => {
  it('starts OAuth with return_surface=mobile', () => {
    const oauth = read('features/integrations/integrationsOAuth.ts');
    assert.match(oauth, /return_surface:\s*MOBILE_RETURN_SURFACE|return_surface:\s*'mobile'/);
  });

  it('parses integrations deep link without tokens', () => {
    const nav = read('app/navigation.ts');
    assert.match(nav, /parseIntegrationsDeepLink/);
    assert.match(nav, /meta_connection/);
    assert.doesNotMatch(nav, /access_token|tenant_id/);
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

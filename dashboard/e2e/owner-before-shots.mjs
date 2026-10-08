import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const out = path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'owner-shots', process.env.SHOTS || 'after');
await mkdir(out, { recursive: true });

const user = {
  id: 'owner-1',
  email: 'portal.desk@linasaibot.com',
  role: 'platform_owner',
  tenantId: 'platform',
  name: 'Owner',
};

const subscribers = {
  success: true,
  subscribers: [
    {
      tenant_id: 'linas',
      business_name: 'Linas Clinic',
      email: 'owner@linas.ai',
      membership: 'active',
      subscription: 'max',
      messages_remaining: 24990,
      historical_credit_remaining: 180858,
      hide_by_default: false,
      intended_price_usd: 279,
      intended_included_messages: 25000,
      users: [{ id: 'u1', email: 'owner@linas.ai', role: 'owner', status: 'active' }],
    },
  ],
  next_cursor: '',
};

const browser = await chromium.launch({ channel: 'chrome' });
const page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
await page.addInitScript((stored) => {
  localStorage.setItem('auth_session', JSON.stringify({
    user: stored,
    timestamp: new Date().toISOString(),
    lastValidatedAt: new Date().toISOString(),
  }));
}, user);
await page.route('**/api/**', async (route) => {
  const url = new URL(route.request().url());
  const path = url.pathname;
  const json = (body) => route.fulfill({ status: 200, contentType: 'application/json', body: JSON.stringify(body) });
  if (path.endsWith('/session')) return json({ success: true, user });
  if (path.includes('/analytics')) return json({ success: true, analytics: { new_users: 2, live_users: 4, subscribers: 1, comments: 3, messages_by_channel: { instagram: 20, facebook: 8 }, live_checkout_mrr_usd: 259, intended_message_mrr_usd: 279, credits_total: 24990, credits_used: 0, credits_remaining: 24990, coverage: { source: 'Postgres dashboard users' } } });
  if (path.includes('/activation-readiness')) return json({ success: true, readiness: { ok: false, blockers: ['message_catalog_unpublished', 'eval_suite_below_800'] } });
  if (path.includes('/users')) return json(subscribers);
  if (path.includes('/message-flows')) return json({ success: true, messages: [] });
  if (path.includes('/traces')) return json({ success: true, traces: [] });
  if (path.includes('/knowledge')) return json({ success: true, entries: [] });
  if (path.includes('/qa')) return json({ success: true, items: [] });
  if (path.includes('/message-catalog')) return json({ success: true, catalog: { plans: [], topup_packs: [], free: {}, published: false, admin_revision: 1 } });
  if (path.includes('/costs')) return json({ success: true, known_usd: 0, pending_or_unpriced: 1, messages: { remaining: 24990 }, by_category: {}, pending_by_category: {}, pending_by_provider: {}, events: [], tenants: [] });
  if (path.includes('/audit')) return json({ success: true, events: [] });
  if (path.includes('/health')) return json({ success: true, database: { status: 'ok', reachable: true, configured: true }, api: 'ok' });
  if (path.includes('/flow/logs')) return json({ success: true, data: [] });
  return json({ success: true });
});

const shots = [
  ['01-overview', '/owner'],
  ['02-users', '/owner/users'],
  ['03-tenants', '/owner/tenants'],
  ['04-messages', '/owner/messages'],
  ['05-traces', '/owner/traces'],
  ['06-copilot', '/owner/copilot'],
  ['07-knowledge', '/owner/knowledge'],
  ['08-qa', '/owner/qa'],
  ['09-catalog', '/owner/catalog'],
  ['10-economy', '/owner/economy'],
  ['11-costs', '/owner/costs'],
  ['12-brains', '/owner/brains'],
  ['13-audit', '/owner/audit'],
  ['14-health', '/owner/health'],
];
for (const [name, route] of shots) {
  await page.goto(`http://127.0.0.1:4174${route}`, { waitUntil: 'networkidle' });
  await page.waitForTimeout(400);
  await page.screenshot({ path: path.join(out, `${name}.png`), fullPage: false });
}
await browser.close();
console.log('before shots', shots.length);

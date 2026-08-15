import { fetchWebChatSettings } from './webChatApi';
import { readWebChatCardSnapshot, writeWebChatCardSnapshot } from './webChatCardCache';
import { fetchWebChannelEntitledFromEntitlements } from './webChatPlanAccess';

/** Warm the in-memory web chat card cache (integrations screen initial load). */
export async function prefetchWebChatCardSnapshot(): Promise<void> {
  const [settings, entitlementWeb] = await Promise.all([
    fetchWebChatSettings(),
    fetchWebChannelEntitledFromEntitlements(),
  ]);
  writeWebChatCardSnapshot({ settings, entitlementWeb });
}

export function hasWebChatCardSnapshot(): boolean {
  return readWebChatCardSnapshot() !== null;
}

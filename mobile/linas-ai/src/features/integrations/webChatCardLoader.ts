import { fetchWebChatSettings } from './webChatApi';
import { readWebChatCardSnapshot, writeWebChatCardSnapshot } from './webChatCardCache';
import { fetchWebChannelEntitledFromEntitlements } from './webChatPlanAccess';

/**
 * Warm the in-memory web chat card cache (integrations screen initial load).
 * Soft-fails: never throws — list load must not depend on web-chat availability.
 */
export async function prefetchWebChatCardSnapshot(): Promise<boolean> {
  try {
    const [settings, entitlementWeb] = await Promise.all([
      fetchWebChatSettings(),
      fetchWebChannelEntitledFromEntitlements(),
    ]);
    writeWebChatCardSnapshot({ settings, entitlementWeb });
    return true;
  } catch {
    return false;
  }
}

export function hasWebChatCardSnapshot(): boolean {
  return readWebChatCardSnapshot() !== null;
}

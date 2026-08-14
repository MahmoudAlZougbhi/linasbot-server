import type { ControlArea } from '../control/controlAreas';
import type { DrawerBadges } from './useDrawerBadges';

export type DrawerTileBadge = { label: string; tone: 'teal' | 'danger' };

/** Drawer tile badge — AI Setup percent, or unread/pending counts. */
export function drawerTileBadge(
  modId: ControlArea,
  badges: DrawerBadges,
): DrawerTileBadge | null {
  if (modId === 'cm' && badges.aiSetupPercent != null && badges.aiSetupPercent < 100) {
    return { label: `${badges.aiSetupPercent}%`, tone: 'teal' };
  }
  if (modId === 'livechat' && badges.liveChatUnread > 0) {
    const n = badges.liveChatUnread > 99 ? '99+' : String(badges.liveChatUnread);
    return { label: n, tone: 'danger' };
  }
  if (modId === 'requests' && badges.requestsPending > 0) {
    const n = badges.requestsPending > 99 ? '99+' : String(badges.requestsPending);
    return { label: n, tone: 'danger' };
  }
  return null;
}

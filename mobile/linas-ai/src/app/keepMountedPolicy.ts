/**
 * Keep-mounted panes stay in RAM after first visit (display:none).
 * Limit is hard: only high-traffic screens whose live state is expensive to rebuild.
 * Everything else unmounts and paints from the query cache.
 */
export const KEEP_MOUNTED_SCREENS = ['chat', 'livechat', 'dashboard', 'cm'] as const;

export type KeepMountedScreen = (typeof KEEP_MOUNTED_SCREENS)[number];

export const KEEP_MOUNTED_LIMIT = KEEP_MOUNTED_SCREENS.length;

export function isKeepMountedScreen(name: string): name is KeepMountedScreen {
  return (KEEP_MOUNTED_SCREENS as readonly string[]).includes(name);
}

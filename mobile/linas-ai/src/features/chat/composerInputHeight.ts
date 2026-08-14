/** Composer field line metrics — keep in sync with ChatComposer `styles.input`. */
export const COMPOSER_INPUT_LINE_HEIGHT = 22;
export const COMPOSER_INPUT_MAX_LINES = 8;
/** Single-line field height — matches + / mic / send inside the compact pill. */
export const COMPOSER_INPUT_MIN_H = 36;
export const COMPOSER_INPUT_MAX_H =
  COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT * (COMPOSER_INPUT_MAX_LINES - 1);
/**
 * iOS `contentSize` for one 16/22 line often equals the view height (36) or a
 * few px more. Stay single-line until content clearly needs another line.
 */
export const COMPOSER_GROW_SLACK = 6;
/** Idle compact pill: pad 4 + 36pt actions + pad 4. */
export const COMPOSER_PILL_MIN_H = 44;
export const COMPOSER_PILL_PAD_V = 4;
/** Bottom icon row in the focused/stacked ChatGPT-style bar. */
export const COMPOSER_ACTION_ROW_H = 36;
/** Stable iOS vertical center for one line inside the compact pill. */
export const COMPOSER_IOS_PAD_TOP = (COMPOSER_INPUT_MIN_H - COMPOSER_INPUT_LINE_HEIGHT) / 2;

export function composerHeightForLines(lines: number): number {
  const n = Math.min(COMPOSER_INPUT_MAX_LINES, Math.max(1, lines));
  return COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT * (n - 1);
}

/** Map measured text height to a discrete line-bucket height. */
export function targetComposerInputHeight(contentHeight: number, draft: string): number {
  if (!draft.trim()) return COMPOSER_INPUT_MIN_H;
  const raw = Math.round(contentHeight);
  const newlineCount = draft.split('\n').length;
  let lines = 1;
  if (raw > COMPOSER_INPUT_MIN_H + COMPOSER_GROW_SLACK) {
    lines = Math.max(2, Math.round(raw / COMPOSER_INPUT_LINE_HEIGHT));
  }
  lines = Math.max(lines, newlineCount);
  return composerHeightForLines(lines);
}

/**
 * Grow immediately so wrapped characters stay visible. Debounce shrink only —
 * iOS contentSize bounce must not flap the bar back down mid-keystroke.
 */
export function debounceComposerHeight(
  target: number,
  current: number,
  pending: number | null,
): { height: number; pending: number | null } {
  if (target === current) return { height: current, pending: null };
  if (target > current) return { height: target, pending: null };
  if (pending === target) return { height: target, pending: null };
  return { height: current, pending: target };
}

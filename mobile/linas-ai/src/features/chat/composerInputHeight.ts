/** Composer field line metrics — keep in sync with ChatComposer `styles.input`. */
export const COMPOSER_INPUT_LINE_HEIGHT = 22;
export const COMPOSER_INPUT_MAX_LINES = 8;
export const COMPOSER_INPUT_PAD_H = 8;
/** Single-line field height — matches + / mic / send inside the compact pill. */
export const COMPOSER_INPUT_MIN_H = 36;
export const COMPOSER_INPUT_MAX_H =
  COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT * (COMPOSER_INPUT_MAX_LINES - 1);
/**
 * iOS often reports `contentSize.height ===` the clipped view (36). That is not
 * a wrap. Only treat contentSize as extra lines when it clearly exceeds min+slack.
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

/** Visible rows from `\n`, including a trailing newline (caret on a new line). */
export function lineCountFromDraft(draft: string): number {
  if (draft.length === 0) return 1;
  return Math.min(COMPOSER_INPUT_MAX_LINES, Math.max(1, draft.split('\n').length));
}

export function composerHeightFromDraft(draft: string): number {
  return composerHeightForLines(lineCountFromDraft(draft));
}

/** Map unconstrained content height to lines. Do not subtract padding (that zeroes the delta). */
export function linesFromContentHeight(contentHeight: number): number {
  const raw = Math.round(contentHeight);
  if (raw <= COMPOSER_INPUT_MIN_H + COMPOSER_GROW_SLACK) return 1;
  return Math.min(
    COMPOSER_INPUT_MAX_LINES,
    Math.max(2, Math.round(raw / COMPOSER_INPUT_LINE_HEIGHT)),
  );
}

export function resolveComposerLineCount(
  draft: string,
  measuredLines = 1,
  contentHeight = 0,
): number {
  if (draft.length === 0) return 1;
  const fromNewlines = lineCountFromDraft(draft);
  if (!draft.trim() && fromNewlines === 1) return 1;
  if (!draft.trim()) return fromNewlines;
  return Math.min(
    COMPOSER_INPUT_MAX_LINES,
    Math.max(fromNewlines, Math.max(1, measuredLines), linesFromContentHeight(contentHeight)),
  );
}

/** Map measured text height + draft to a discrete line-bucket height. */
export function targetComposerInputHeight(
  contentHeight: number,
  draft: string,
  measuredLines = 1,
): number {
  return composerHeightForLines(resolveComposerLineCount(draft, measuredLines, contentHeight));
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

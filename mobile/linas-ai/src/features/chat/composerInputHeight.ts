/** Composer field line metrics — keep in sync with ChatComposer `styles.input`. */
export const COMPOSER_INPUT_LINE_HEIGHT = 22;
export const COMPOSER_INPUT_MAX_LINES = 8;
export const COMPOSER_INPUT_PAD_H = 8;
/** Single-line field height — matches + / mic / send inside the compact pill. */
export const COMPOSER_INPUT_MIN_H = 36;
export const COMPOSER_INPUT_MAX_H =
  COMPOSER_INPUT_MIN_H + COMPOSER_INPUT_LINE_HEIGHT * (COMPOSER_INPUT_MAX_LINES - 1);
/** Hidden wrap probe must have a real field width; ignore layout before that. */
export const COMPOSER_MIN_PROBE_WIDTH = 80;
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

/** Uncapped rows from `\n`, including a trailing newline (caret on a new line). */
export function newlineCount(draft: string): number {
  if (draft.length === 0) return 1;
  return Math.max(1, draft.split('\n').length);
}

/** Visible bar rows — never more than 8. */
export function visibleComposerLines(totalLines: number): number {
  return Math.min(COMPOSER_INPUT_MAX_LINES, Math.max(1, totalLines));
}

export function composerExceedsMaxLines(totalLines: number): boolean {
  return totalLines > COMPOSER_INPUT_MAX_LINES;
}

/** Capped bar row count from explicit newlines (1…8). */
export function lineCountFromDraft(draft: string): number {
  return visibleComposerLines(newlineCount(draft));
}

export function composerHeightFromDraft(draft: string): number {
  return composerHeightForLines(visibleComposerLines(newlineCount(draft)));
}

/**
 * Integer line buckets from explicit newlines and wrap measure only.
 * Do not feed iOS `contentSize` here — the clipped view height echoes the
 * current bar and `round(height / 22)` cascades 2→3→…→8 every keystroke.
 */
export function resolveComposerLineCount(draft: string, measuredWraps = 1): number {
  if (draft.length === 0) return 1;
  const fromNewlines = newlineCount(draft);
  if (!draft.trim()) return fromNewlines;
  const wraps = Math.max(1, Math.floor(measuredWraps));
  return Math.max(fromNewlines, wraps);
}

export function targetComposerInputHeight(draft: string, measuredWraps = 1): number {
  return composerHeightForLines(
    visibleComposerLines(resolveComposerLineCount(draft, measuredWraps)),
  );
}

export function composerLineBucketChanged(prevLines: number, nextLines: number): boolean {
  return Math.max(1, prevLines) !== Math.max(1, nextLines);
}

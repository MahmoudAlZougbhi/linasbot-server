import { useEffect, useRef, useState, type RefObject } from 'react';
import { TextInput } from 'react-native';

import {
  COMPOSER_INPUT_MAX_H,
  COMPOSER_INPUT_MAX_LINES,
  COMPOSER_INPUT_MIN_H,
  composerExceedsMaxLines,
  composerHeightForLines,
  composerLineBucketChanged,
  resolveComposerLineCount,
  visibleComposerLines,
} from './composerInputHeight';

export {
  COMPOSER_INPUT_LINE_HEIGHT,
  COMPOSER_INPUT_MAX_H,
  COMPOSER_INPUT_MAX_LINES,
  COMPOSER_ACTION_ROW_H,
  COMPOSER_INPUT_MIN_H,
  COMPOSER_IOS_PAD_TOP,
  COMPOSER_PILL_MIN_H,
  COMPOSER_PILL_PAD_V,
} from './composerInputHeight';

/** RN multiline TextInput exposes ScrollView-like scrollToEnd at runtime. */
type ScrollableTextInput = TextInput & {
  scrollToEnd?: (options?: { animated?: boolean }) => void;
};

/**
 * Auto-grow composer by integer line buckets (1…8). Wrap count comes from the
 * hidden measure Text only — iOS `onContentSizeChange` is ignored so view-height
 * echo cannot cascade the bar to 8 or jitter every keystroke.
 */
export function useComposerInputAutoGrow(
  draft: string,
  inputRef?: RefObject<TextInput | null>,
) {
  const [inputHeight, setInputHeight] = useState(COMPOSER_INPUT_MIN_H);
  const [totalLines, setTotalLines] = useState(1);
  const localInputRef = useRef<TextInput | null>(null);
  const heightRef = useRef(COMPOSER_INPUT_MIN_H);
  const totalLinesRef = useRef(1);
  const measuredWrapsRef = useRef(1);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const visibleLines = visibleComposerLines(totalLines);
  const atMaxHeight = visibleLines >= COMPOSER_INPUT_MAX_LINES;
  const showExpandControl = composerExceedsMaxLines(totalLines);

  function assignInputRef(node: TextInput | null) {
    localInputRef.current = node;
    if (inputRef) {
      (inputRef as { current: TextInput | null }).current = node;
    }
  }

  function scrollComposerToEnd() {
    const node = localInputRef.current as ScrollableTextInput | null;
    node?.scrollToEnd?.({ animated: false });
  }

  function commitTotalLines(nextTotal: number) {
    const n = Math.max(1, nextTotal);
    if (!composerLineBucketChanged(totalLinesRef.current, n)) return;
    totalLinesRef.current = n;
    setTotalLines(n);
    const nextH = composerHeightForLines(visibleComposerLines(n));
    if (nextH !== heightRef.current) {
      heightRef.current = nextH;
      setInputHeight(nextH);
    }
    if (nextH >= COMPOSER_INPUT_MAX_H) {
      requestAnimationFrame(scrollComposerToEnd);
    }
  }

  function commitFromDraftAndWraps() {
    const currentDraft = draftRef.current;
    if (currentDraft.length === 0) {
      measuredWrapsRef.current = 1;
      commitTotalLines(1);
      return;
    }
    commitTotalLines(resolveComposerLineCount(currentDraft, measuredWrapsRef.current));
  }

  function handleMeasuredLines(measuredWraps: number) {
    const wraps = Math.max(1, Math.floor(measuredWraps));
    if (wraps === measuredWrapsRef.current) return;
    measuredWrapsRef.current = wraps;
    commitFromDraftAndWraps();
  }

  function handleChangeText(next: string, onChangeDraft: (v: string) => void) {
    draftRef.current = next;
    onChangeDraft(next);
    commitFromDraftAndWraps();
    if (heightRef.current >= COMPOSER_INPUT_MAX_H) {
      requestAnimationFrame(scrollComposerToEnd);
    }
  }

  useEffect(() => {
    draftRef.current = draft;
    commitFromDraftAndWraps();
  }, [draft]);

  return {
    inputHeight,
    totalLines,
    visibleLines,
    atMaxHeight,
    showExpandControl,
    localInputRef,
    assignInputRef,
    handleChangeText,
    handleMeasuredLines,
    scrollComposerToEnd,
  };
}

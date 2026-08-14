import { useEffect, useRef, useState, type RefObject } from 'react';
import { TextInput } from 'react-native';

import {
  COMPOSER_INPUT_MAX_H,
  COMPOSER_INPUT_MIN_H,
  debounceComposerHeight,
  targetComposerInputHeight,
} from './composerInputHeight';

export {
  COMPOSER_GROW_SLACK,
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
 * Auto-grow composer field up to 8 lines; once capped, scrollToEnd so the
 * caret / newest text stays visible.
 *
 * Height is driven from the draft (newlines) and a hidden measure Text, not
 * from iOS `onContentSizeChange` alone. A fixed 36pt TextInput makes iOS
 * report contentSize === 36 forever, so waiting on that event never grows.
 */
export function useComposerInputAutoGrow(
  draft: string,
  inputRef?: RefObject<TextInput | null>,
) {
  const [inputHeight, setInputHeight] = useState(COMPOSER_INPUT_MIN_H);
  const localInputRef = useRef<TextInput | null>(null);
  const heightRef = useRef(COMPOSER_INPUT_MIN_H);
  const pendingRef = useRef<number | null>(null);
  const measuredLinesRef = useRef(1);
  const draftRef = useRef(draft);
  draftRef.current = draft;
  const atMaxHeight = inputHeight >= COMPOSER_INPUT_MAX_H;

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

  function commitHeight(next: number) {
    if (next === heightRef.current) return;
    heightRef.current = next;
    setInputHeight(next);
    if (next >= COMPOSER_INPUT_MAX_H) {
      requestAnimationFrame(scrollComposerToEnd);
    }
  }

  function commitFromDraftAndMeasure() {
    const currentDraft = draftRef.current;
    if (currentDraft.length === 0) {
      pendingRef.current = null;
      measuredLinesRef.current = 1;
      commitHeight(COMPOSER_INPUT_MIN_H);
      return;
    }
    const target = targetComposerInputHeight(0, currentDraft, measuredLinesRef.current);
    pendingRef.current = null;
    commitHeight(target);
  }

  function handleContentSizeChange(contentHeight: number) {
    const currentDraft = draftRef.current;
    if (currentDraft.length === 0) {
      commitFromDraftAndMeasure();
      return;
    }
    const target = targetComposerInputHeight(
      contentHeight,
      currentDraft,
      measuredLinesRef.current,
    );
    if (target > heightRef.current) {
      pendingRef.current = null;
      commitHeight(target);
      return;
    }
    const next = debounceComposerHeight(target, heightRef.current, pendingRef.current);
    pendingRef.current = next.pending;
    commitHeight(next.height);
  }

  function handleMeasuredLines(measuredLines: number) {
    measuredLinesRef.current = Math.max(1, measuredLines);
    commitFromDraftAndMeasure();
  }

  function handleChangeText(next: string, onChangeDraft: (v: string) => void) {
    draftRef.current = next;
    onChangeDraft(next);
    commitFromDraftAndMeasure();
    if (heightRef.current >= COMPOSER_INPUT_MAX_H) {
      requestAnimationFrame(scrollComposerToEnd);
    }
  }

  useEffect(() => {
    commitFromDraftAndMeasure();
  }, [draft]);

  return {
    inputHeight,
    atMaxHeight,
    localInputRef,
    assignInputRef,
    handleContentSizeChange,
    handleChangeText,
    handleMeasuredLines,
  };
}

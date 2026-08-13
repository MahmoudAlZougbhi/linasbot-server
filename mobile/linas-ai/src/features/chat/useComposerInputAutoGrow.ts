import { useEffect, useRef, useState, type RefObject } from 'react';
import { TextInput } from 'react-native';

/** Composer field line metrics — keep in sync with ChatComposer `styles.input`. */
export const COMPOSER_INPUT_LINE_HEIGHT = 22;
export const COMPOSER_INPUT_MAX_LINES = 8;
/** Single-line height inside the 48px pill (padding + icons). */
export const COMPOSER_INPUT_MIN_H = 36;
export const COMPOSER_INPUT_MAX_H = COMPOSER_INPUT_LINE_HEIGHT * COMPOSER_INPUT_MAX_LINES;

/** RN multiline TextInput exposes ScrollView-like scrollToEnd at runtime. */
type ScrollableTextInput = TextInput & {
  scrollToEnd?: (options?: { animated?: boolean }) => void;
};

/**
 * Auto-grow composer field up to 8 lines; once capped, scrollToEnd so the
 * caret / newest text stays visible.
 */
export function useComposerInputAutoGrow(
  draft: string,
  inputRef?: RefObject<TextInput | null>,
) {
  const [inputHeight, setInputHeight] = useState(COMPOSER_INPUT_MIN_H);
  const localInputRef = useRef<TextInput | null>(null);
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

  function handleContentSizeChange(contentHeight: number) {
    const contentH = Math.ceil(contentHeight);
    const next = Math.min(
      COMPOSER_INPUT_MAX_H,
      Math.max(COMPOSER_INPUT_MIN_H, contentH),
    );
    setInputHeight(next);
    if (contentH >= COMPOSER_INPUT_MAX_H) {
      requestAnimationFrame(scrollComposerToEnd);
    }
  }

  function handleChangeText(next: string, onChangeDraft: (v: string) => void) {
    onChangeDraft(next);
    // Voice append / paste can grow past the cap without a fresh size event
    // on the same frame — keep the caret end visible once capped.
    if (atMaxHeight) requestAnimationFrame(scrollComposerToEnd);
  }

  useEffect(() => {
    if (!draft.trim()) setInputHeight(COMPOSER_INPUT_MIN_H);
  }, [draft]);

  return {
    inputHeight,
    atMaxHeight,
    localInputRef,
    assignInputRef,
    handleContentSizeChange,
    handleChangeText,
  };
}

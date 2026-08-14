/**
 * Per-message text direction from content script (not app locale).
 * Uses the first strong bidirectional character (Unicode BiDi paragraph heuristic)
 * so English stays LTR even when I18nManager.forceRTL is on for Arabic UI chrome.
 */

import { I18nManager, type FlexAlignType, type ViewStyle } from 'react-native';

/** Pull AI rows into list padding so LTR hugs left / RTL hugs right harder. */
export const AI_MESSAGE_EDGE_HUG = 10;

function isNeutralOrWeak(cp: number): boolean {
  // ASCII controls, space, digits, most punctuation
  if (cp <= 0x40) return true;
  if (cp >= 0x5b && cp <= 0x60) return true;
  if (cp >= 0x7b && cp <= 0xbf) return true;
  // Combining marks (incl. Arabic harakat — skip so base letter wins)
  if (cp >= 0x0300 && cp <= 0x036f) return true;
  if (cp >= 0x064b && cp <= 0x065f) return true;
  if (cp === 0x0670) return true;
  // General punctuation / format / currency / emoji presentation
  if (cp >= 0x2000 && cp <= 0x206f) return true;
  if (cp >= 0x20a0 && cp <= 0x20cf) return true;
  if (cp >= 0xfe00 && cp <= 0xfe0f) return true;
  if (cp >= 0x1f300 && cp <= 0x1faff) return true;
  return false;
}

function isRtlStrong(cp: number): boolean {
  return (
    (cp >= 0x0590 && cp <= 0x05ff) || // Hebrew
    (cp >= 0x0600 && cp <= 0x06ff) || // Arabic
    (cp >= 0x0700 && cp <= 0x074f) || // Syriac
    (cp >= 0x0750 && cp <= 0x077f) || // Arabic Supplement
    (cp >= 0x0780 && cp <= 0x07bf) || // Thaana
    (cp >= 0x07c0 && cp <= 0x07ff) || // NKo
    (cp >= 0x0800 && cp <= 0x083f) || // Samaritan
    (cp >= 0x0840 && cp <= 0x085f) || // Mandaic
    (cp >= 0x08a0 && cp <= 0x08ff) || // Arabic Extended-A
    (cp >= 0xfb1d && cp <= 0xfdff) || // Hebrew/Arabic presentation forms
    (cp >= 0xfe70 && cp <= 0xfeff) // Arabic presentation forms-B
  );
}

/** True when the message's first strong character is an RTL script letter. */
export function isRtlText(text: string | null | undefined): boolean {
  if (!text) return false;
  for (let i = 0; i < text.length; ) {
    const cp = text.codePointAt(i) as number;
    i += cp > 0xffff ? 2 : 1;
    if (isNeutralOrWeak(cp)) continue;
    return isRtlStrong(cp);
  }
  return false;
}

export type TextDirectionStyle = {
  textAlign: 'left' | 'right';
  writingDirection: 'ltr' | 'rtl';
};

/** Explicit LTR/RTL so app-locale I18nManager RTL cannot flip English bubbles. */
export function textDirectionStyle(text: string | null | undefined): TextDirectionStyle {
  if (isRtlText(text)) {
    return { textAlign: 'right', writingDirection: 'rtl' };
  }
  return { textAlign: 'left', writingDirection: 'ltr' };
}

/**
 * flex-start/end toward the message script's physical start edge.
 * Compensates for I18nManager.forceRTL flipping start/end.
 */
export function contentStartAlign(text: string | null | undefined): FlexAlignType {
  const rtl = isRtlText(text);
  return I18nManager.isRTL === rtl ? 'flex-start' : 'flex-end';
}

/**
 * AI row layout: stretch across the list so short EN sits left and short AR sits right,
 * then hug the matching screen edge (stronger than textAlign alone).
 */
export function aiMessageRowStyle(text: string | null | undefined): ViewStyle {
  const rtl = isRtlText(text);
  return {
    alignSelf: 'stretch',
    maxWidth: '100%',
    marginLeft: rtl ? 0 : -AI_MESSAGE_EDGE_HUG,
    marginRight: rtl ? -AI_MESSAGE_EDGE_HUG : 0,
  };
}

/** Body / actions: pack toward the script's physical start edge. Not the brand header. */
export function aiMessageColStyle(text: string | null | undefined): ViewStyle {
  return { alignItems: contentStartAlign(text) };
}

/**
 * Sparkle + Linas name: always physical left / LTR, never follows message RTL.
 */
export const aiMessageHeaderStyle: ViewStyle = {
  alignSelf: 'flex-start',
  direction: 'ltr',
};

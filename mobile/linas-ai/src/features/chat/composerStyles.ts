import { StyleSheet } from 'react-native';

import { fonts, radii, spacing } from '../../theme';
import { COMPOSER_ACTION_SIZE, COMPOSER_SEND_SIZE } from './ComposerGlyphs';
import {
  COMPOSER_INPUT_LINE_HEIGHT,
  COMPOSER_INPUT_MIN_H,
  COMPOSER_PILL_MIN_H,
  COMPOSER_PILL_PAD_V,
} from './composerInputHeight';

/** Compact single-row pill (+ | field | mic | send). Idle height is 44pt. */
export const composerStyles = StyleSheet.create({
  wrap: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    direction: 'ltr',
  },
  pill: {
    flexDirection: 'row',
    borderRadius: radii.pill,
    paddingVertical: COMPOSER_PILL_PAD_V,
    paddingLeft: 6,
    paddingRight: 6,
    minHeight: COMPOSER_PILL_MIN_H,
    gap: 2,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  pillSingle: {
    alignItems: 'center',
  },
  pillGrow: {
    alignItems: 'flex-end',
    paddingBottom: COMPOSER_PILL_PAD_V,
  },
  inputSlot: {
    flex: 1,
    minWidth: 0,
    minHeight: COMPOSER_INPUT_MIN_H,
    justifyContent: 'center',
  },
  placeholderWrap: {
    position: 'absolute',
    top: 0,
    left: 0,
    right: 0,
    bottom: 0,
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  placeholderText: {
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: COMPOSER_INPUT_LINE_HEIGHT,
  },
  input: {
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: COMPOSER_INPUT_LINE_HEIGHT,
    paddingHorizontal: 8,
    paddingVertical: 0,
    includeFontPadding: false,
  },
  iconHit: {
    width: COMPOSER_ACTION_SIZE,
    height: COMPOSER_ACTION_SIZE,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  sendInside: {
    width: COMPOSER_SEND_SIZE,
    height: COMPOSER_SEND_SIZE,
    borderRadius: COMPOSER_SEND_SIZE / 2,
    alignItems: 'center',
    justifyContent: 'center',
    flexShrink: 0,
  },
  sendBusy: { opacity: 0.7 },
  disclaimer: {
    fontFamily: fonts.body,
    fontSize: 11,
    textAlign: 'center',
    marginTop: 8,
  },
});

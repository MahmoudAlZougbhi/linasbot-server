import { StyleSheet } from 'react-native';

import { fonts, radii, spacing } from '../../theme';
import { COMPOSER_ACTION_SIZE, COMPOSER_SEND_SIZE } from './ComposerGlyphs';
import {
  COMPOSER_ACTION_ROW_H,
  COMPOSER_INPUT_LINE_HEIGHT,
  COMPOSER_PILL_MIN_H,
  COMPOSER_PILL_PAD_V,
} from './composerInputHeight';

/** Compact idle row, or stacked focused bar (text top, icons bottom). */
export const composerStyles = StyleSheet.create({
  wrap: {
    paddingHorizontal: spacing.md,
    paddingTop: spacing.sm,
    direction: 'ltr',
    alignSelf: 'stretch',
    flexShrink: 0,
  },
  pill: {
    alignSelf: 'stretch',
    paddingLeft: 6,
    paddingRight: 6,
    minHeight: COMPOSER_PILL_MIN_H,
    shadowOffset: { width: 0, height: 1 },
    shadowOpacity: 0.1,
    shadowRadius: 8,
    elevation: 3,
  },
  pillCompact: {
    flexDirection: 'row',
    alignItems: 'center',
    height: COMPOSER_PILL_MIN_H,
    borderRadius: radii.pill,
    paddingVertical: COMPOSER_PILL_PAD_V,
    gap: 2,
  },
  pillStacked: {
    flexDirection: 'column',
    alignItems: 'stretch',
    borderRadius: radii.xl,
    paddingTop: 10,
    paddingBottom: 6,
    gap: 4,
  },
  inputSlot: {
    flex: 1,
    minWidth: 0,
    justifyContent: 'center',
  },
  inputSlotStacked: {
    alignSelf: 'stretch',
    width: '100%',
    minWidth: 0,
    justifyContent: 'flex-start',
  },
  input: {
    width: '100%',
    fontFamily: fonts.body,
    fontSize: 16,
    lineHeight: COMPOSER_INPUT_LINE_HEIGHT,
    paddingHorizontal: 8,
    paddingVertical: 0,
    includeFontPadding: false,
  },
  actionRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    height: COMPOSER_ACTION_ROW_H,
    width: '100%',
    flexShrink: 0,
  },
  actionRight: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 2,
    flexShrink: 0,
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

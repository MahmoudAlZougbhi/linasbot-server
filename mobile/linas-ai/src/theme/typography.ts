import { Platform, TextStyle } from 'react-native';

/** Distinctive system faces — no Inter/Roboto defaults, no extra native deps. */
const display = Platform.select({
  ios: 'AvenirNext-DemiBold',
  android: 'sans-serif-medium',
  default: 'System',
});

const body = Platform.select({
  ios: 'AvenirNext-Regular',
  android: 'sans-serif',
  default: 'System',
});

const bodyMedium = Platform.select({
  ios: 'AvenirNext-Medium',
  android: 'sans-serif-medium',
  default: 'System',
});

export const fonts = {
  display,
  body,
  bodyMedium,
} as const;

export const typography = {
  hero: {
    fontFamily: display,
    fontSize: 36,
    letterSpacing: 0.4,
    color: undefined,
  } satisfies TextStyle,
  title: {
    fontFamily: display,
    fontSize: 26,
    letterSpacing: 0.2,
  } satisfies TextStyle,
  subtitle: {
    fontFamily: body,
    fontSize: 16,
    lineHeight: 22,
  } satisfies TextStyle,
  body: {
    fontFamily: body,
    fontSize: 16,
    lineHeight: 23,
  } satisfies TextStyle,
  bodyStrong: {
    fontFamily: bodyMedium,
    fontSize: 16,
    lineHeight: 22,
  } satisfies TextStyle,
  caption: {
    fontFamily: body,
    fontSize: 13,
    lineHeight: 18,
  } satisfies TextStyle,
  label: {
    fontFamily: bodyMedium,
    fontSize: 14,
    letterSpacing: 0.3,
  } satisfies TextStyle,
  /** Chat message body — user bubble and AI plain text share one scale (ChatGPT-style). */
  chatAi: {
    fontFamily: body,
    fontSize: 16,
    lineHeight: 23,
  } satisfies TextStyle,
  chatUser: {
    fontFamily: body,
    fontSize: 16,
    lineHeight: 23,
  } satisfies TextStyle,
} as const;

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
  /** Card/section heading — matches Dashboard “Total activity” titles. */
  sectionTitle: {
    fontFamily: bodyMedium,
    fontSize: 16,
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
  /**
   * Sidebar module tiles + chat titles — same 16px, medium fill like ChatGPT.
   * Do not change size here without updating both DrawerNavGrid and HistoryRows.
   */
  drawerItem: {
    fontFamily: bodyMedium,
    fontSize: 16,
    lineHeight: 22,
    letterSpacing: -0.15,
  } satisfies TextStyle,
  /** Owner Copilot AI reply — same 17px, medium fill (not larger). */
  chatAi: {
    fontFamily: bodyMedium,
    fontSize: 17,
    lineHeight: 24,
  } satisfies TextStyle,
  chatUser: {
    fontFamily: bodyMedium,
    fontSize: 16,
    lineHeight: 23,
  } satisfies TextStyle,
} as const;

import { StyleSheet, Text, View } from 'react-native';

import { useReduceMotion } from '../../hooks/useReduceMotion';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { useWelcomeTypewriter } from './useWelcomeTypewriter';

/** Signed-in New Chat empty state with a tasteful typewriter welcome loop. */
export function OwnerEmptyState() {
  const { tr } = useI18n();
  const { colors } = useTheme();
  const reduceMotion = useReduceMotion();
  const title = tr('chatEmptyTitle');
  const body = tr('chatEmptyBody');
  const { titleShown, bodyShown, cursorLine, cursorOn } = useWelcomeTypewriter(
    title,
    body,
    !reduceMotion,
  );

  return (
    <View style={styles.wrap} accessibilityLabel={`${title}. ${body}`}>
      <Text style={[styles.title, { color: colors.text }]}>
        {titleShown}
        {cursorLine === 'title' && cursorOn ? (
          <Text style={{ color: colors.accent }}>|</Text>
        ) : null}
      </Text>
      <Text style={[styles.body, { color: colors.textMuted }]}>
        {bodyShown}
        {cursorLine === 'body' && cursorOn ? (
          <Text style={{ color: colors.accent }}>|</Text>
        ) : null}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 24 },
  title: {
    fontFamily: fonts.display,
    fontSize: 22,
    textAlign: 'center',
  },
  body: {
    fontFamily: fonts.body,
    fontSize: 15,
    textAlign: 'center',
    marginTop: spacing.sm,
    lineHeight: 22,
  },
});

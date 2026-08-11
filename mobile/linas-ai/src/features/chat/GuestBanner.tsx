import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';

type Props = {
  gated?: boolean;
  onLogin?: () => void;
};

/** Shown only after the hard guest gate — never as a remaining-count meter. */
export function GuestBanner({ gated, onLogin }: Props) {
  const { tr } = useI18n();
  if (!gated) return null;
  return (
    <View style={[styles.wrap, styles.gated]}>
      <Text style={styles.text}>{tr('guestLimitReached')}</Text>
      {onLogin ? (
        <Pressable onPress={onLogin} style={styles.cta}>
          <Text style={styles.ctaText}>{tr('loginOrRegister')}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: {
    marginHorizontal: spacing.lg,
    marginTop: spacing.sm,
    marginBottom: 4,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm + 2,
    borderRadius: radii.md,
    backgroundColor: colors.banner,
    borderWidth: 1,
    borderColor: colors.bannerBorder,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
  },
  gated: {
    backgroundColor: '#FEF3C7',
    borderColor: '#FCD34D',
    flexWrap: 'wrap',
  },
  text: {
    flex: 1,
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 13,
    lineHeight: 18,
  },
  cta: {
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: radii.pill,
    backgroundColor: colors.accent,
  },
  ctaText: { color: colors.onAccent, fontFamily: fonts.bodyMedium, fontSize: 12 },
});

import { Pressable, StyleSheet, Text, View } from 'react-native';

import { LinasStarMark } from '../../components/LinasStarMark';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { fonts, radii, spacing, useTheme } from '../../theme';

const GUEST_STARTERS: {
  id: string;
  titleKey: StringKey;
  subtitleKey: StringKey;
  promptEn: string;
}[] = [
  {
    id: 'what',
    titleKey: 'guestStarterWhatTitle',
    subtitleKey: 'guestStarterWhatSub',
    promptEn: 'What can Linas AI do for my business?',
  },
  {
    id: 'dm',
    titleKey: 'guestStarterDmTitle',
    subtitleKey: 'guestStarterDmSub',
    promptEn: 'How does Linas handle social media DMs and comments?',
  },
  {
    id: 'connect',
    titleKey: 'guestStarterConnectTitle',
    subtitleKey: 'guestStarterConnectSub',
    promptEn: 'How do I connect my business after I sign in?',
  },
];

type Props = {
  onPick: (prompt: string) => void;
};

export function GuestEmptyState({ onPick }: Props) {
  const { tr, language } = useI18n();
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <LinasStarMark size={42} />
      <Text style={[styles.title, { color: colors.text }]}>{tr('guestHowCanHelp')}</Text>
      <Text style={[styles.body, { color: colors.textMuted }]}>{tr('guestAskWhat')}</Text>
      <View style={styles.cards}>
        {GUEST_STARTERS.map((s) => {
          const title = tr(s.titleKey);
          const prompt = language === 'en' ? s.promptEn : title;
          return (
            <Pressable
              key={s.id}
              style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
              onPress={() => onPick(prompt)}
              accessibilityLabel={title}
              accessibilityRole="button"
            >
              <View style={{ flex: 1 }}>
                <Text style={[styles.cardTitle, { color: colors.text }]}>{title}</Text>
                <Text style={{ color: colors.textMuted, fontSize: 12 }}>{tr(s.subtitleKey)}</Text>
              </View>
              <Text style={{ color: colors.textDim }}>›</Text>
            </Pressable>
          );
        })}
      </View>
      <Text style={[styles.hint, { color: colors.textDim }]}>{tr('guestAccessHint')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingVertical: 28, paddingHorizontal: 20, alignItems: 'center' },
  title: {
    fontFamily: fonts.display,
    fontSize: 26,
    marginTop: spacing.lg,
    textAlign: 'center',
  },
  body: {
    fontFamily: fonts.body,
    fontSize: 14,
    textAlign: 'center',
    marginTop: spacing.sm,
    maxWidth: 320,
  },
  cards: { width: '100%', gap: 10, marginTop: spacing.xl },
  card: {
    minHeight: 64,
    borderRadius: radii.lg,
    borderWidth: 1,
    paddingHorizontal: spacing.lg,
    paddingVertical: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
  },
  cardTitle: { fontFamily: fonts.bodyMedium, fontSize: 15 },
  hint: { marginTop: spacing.lg, fontSize: 12, textAlign: 'center' },
});

import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts } from '../../theme';

type Props = {
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
};

/** Pre-Meta confirmation. Continue is the only path that opens Embedded Signup. */
export function WhatsAppCoexistenceConfirm({ busy, onConfirm, onCancel }: Props) {
  const { tr } = useI18n();
  return (
    <View accessibilityRole="summary" style={styles.wrap}>
      <Text style={styles.title}>{tr('waKeepUsingTitle')}</Text>
      <Text style={styles.body}>{tr('waCoexistenceHint')}</Text>
      <Text style={styles.body}>{tr('waDoNotAddNewNumber')}</Text>
      <Pressable
        accessibilityRole="button"
        disabled={busy}
        onPress={onConfirm}
        style={styles.primary}
      >
        <Text style={styles.primaryLabel}>{tr('waConfirmContinue')}</Text>
      </Pressable>
      <Pressable accessibilityRole="button" disabled={busy} onPress={onCancel} style={styles.secondary}>
        <Text style={styles.secondaryLabel}>{tr('waConfirmCancel')}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 10, paddingTop: 4 },
  title: { color: colors.text, fontSize: 16, lineHeight: 22, fontFamily: fonts.bodyMedium },
  body: { color: colors.textMuted, fontSize: 13, lineHeight: 19, fontFamily: fonts.body },
  primary: {
    backgroundColor: colors.accent,
    borderRadius: 10,
    minHeight: 44,
    paddingVertical: 12,
    paddingHorizontal: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  primaryLabel: { color: colors.onAccent, fontSize: 15, fontFamily: fonts.bodyMedium },
  secondary: { minHeight: 44, paddingVertical: 10, alignItems: 'center', justifyContent: 'center' },
  secondaryLabel: { color: colors.textMuted, fontSize: 14, fontFamily: fonts.body },
});

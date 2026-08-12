import { Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { LEGAL_URLS } from '../../config';
import type { StringKey } from '../../i18n';
import { fonts, spacing, useTheme } from '../../theme';

type Props = {
  tr: (key: StringKey) => string;
  showRefund: boolean;
  busy: boolean;
  onRestore: () => void;
  onManage: () => void;
  onRefund: () => void;
};

export function BillingStoreActions({
  tr,
  showRefund,
  busy,
  onRestore,
  onManage,
  onRefund,
}: Props) {
  const { colors } = useTheme();
  return (
    <View style={[styles.footer, { borderColor: colors.border }]}>
      <Text style={[styles.footerText, { color: colors.textMuted }]}>{tr('subFooterStoreApple')}</Text>
      <Text style={[styles.footerText, { color: colors.textMuted }]}>{tr('subFooterReset')}</Text>
      <Text style={[styles.footerText, { color: colors.textMuted }]}>{tr('subFooterPurchased')}</Text>

      <Pressable onPress={onRestore} disabled={busy} accessibilityRole="button">
        <Text style={[styles.link, { color: colors.accent }]}>{tr('subRestore')}</Text>
      </Pressable>
      <Pressable onPress={onManage} disabled={busy} accessibilityRole="button">
        <Text style={[styles.link, { color: colors.accent }]}>{tr('subManage')}</Text>
      </Pressable>
      {showRefund ? (
        <Pressable onPress={onRefund} disabled={busy} accessibilityRole="button">
          <Text style={[styles.link, { color: colors.accent }]}>{tr('subRequestRefund')}</Text>
        </Pressable>
      ) : null}

      <View style={styles.legalRow}>
        <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.terms)}>
          <Text style={[styles.link, { color: colors.accent }]}>{tr('terms')}</Text>
        </Pressable>
        <Text style={{ color: colors.textDim }}> · </Text>
        <Pressable onPress={() => void Linking.openURL(LEGAL_URLS.privacy)}>
          <Text style={[styles.link, { color: colors.accent }]}>{tr('privacy')}</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  footer: {
    borderTopWidth: 1,
    paddingTop: spacing.md,
    gap: 8,
    marginTop: spacing.sm,
  },
  footerText: { fontFamily: fonts.body, fontSize: 12, lineHeight: 17 },
  legalRow: { flexDirection: 'row', alignItems: 'center', marginTop: 4 },
  link: { fontFamily: fonts.bodyMedium, fontSize: 13 },
});

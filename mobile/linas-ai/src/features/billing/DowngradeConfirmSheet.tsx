import {
  ActivityIndicator,
  Modal,
  Pressable,
  StyleSheet,
  Text,
  View,
} from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import type { StringKey } from '../../i18n';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { PlanId } from './planCatalog';
import { PLAN_NAME_KEY } from './planEntitlements';

type Props = {
  visible: boolean;
  planId: PlanId;
  effectiveDateLabel: string;
  purchasing: boolean;
  tr: (key: StringKey) => string;
  onConfirm: () => void;
  onClose: () => void;
};

export function DowngradeConfirmSheet({
  visible,
  planId,
  effectiveDateLabel,
  purchasing,
  tr,
  onConfirm,
  onClose,
}: Props) {
  const { colors } = useTheme();
  const insets = useSafeAreaInsets();
  const planName = tr(PLAN_NAME_KEY[planId]);
  const body = tr('subDowngradeConfirmBody')
    .replace('{plan}', planName)
    .replace('{date}', effectiveDateLabel);

  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={[styles.scrim, { backgroundColor: colors.overlay }]} onPress={onClose}>
        <Pressable
          style={[
            styles.sheet,
            { backgroundColor: colors.surface, paddingBottom: Math.max(insets.bottom, 16) + 8 },
          ]}
          onPress={(e) => e.stopPropagation()}
        >
          <View style={[styles.handle, { backgroundColor: colors.border }]} />
          <Text style={[styles.title, { color: colors.text }]}>{tr('subDowngradeConfirmTitle')}</Text>
          <Text style={[styles.body, { color: colors.textMuted }]}>{body}</Text>
          <Text style={[styles.note, { color: colors.textMuted }]}>{tr('subDowngradeConfirmNote')}</Text>
          <Pressable
            onPress={onConfirm}
            disabled={purchasing}
            accessibilityRole="button"
            accessibilityLabel={tr('subDowngradeConfirmCta')}
            style={({ pressed }) => [
              styles.cta,
              { backgroundColor: colors.accent, opacity: pressed || purchasing ? 0.88 : 1 },
            ]}
          >
            {purchasing ? (
              <ActivityIndicator color={colors.onAccent} />
            ) : (
              <Text style={[styles.ctaText, { color: colors.onAccent }]}>
                {tr('subDowngradeConfirmCta')}
              </Text>
            )}
          </Pressable>
          <Pressable
            onPress={onClose}
            disabled={purchasing}
            accessibilityRole="button"
            accessibilityLabel={tr('subCancel')}
            style={styles.cancel}
          >
            <Text style={[styles.cancelText, { color: colors.textMuted }]}>{tr('subCancel')}</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: 'flex-end' },
  sheet: {
    borderTopLeftRadius: radii.lg,
    borderTopRightRadius: radii.lg,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    gap: 12,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    marginBottom: 4,
  },
  title: { fontFamily: fonts.display, fontSize: 22, fontWeight: '700' },
  body: { fontFamily: fonts.body, fontSize: 15, lineHeight: 22 },
  note: { fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  cta: {
    borderRadius: radii.md,
    paddingVertical: 16,
    alignItems: 'center',
    marginTop: 4,
  },
  ctaText: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  cancel: { alignItems: 'center', paddingVertical: 10 },
  cancelText: { fontFamily: fonts.bodyMedium, fontSize: 15 },
});

import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppModal } from '../../components/AppModal';
import { ModalScrim } from '../../components/ModalScrim';

import { AppIcon, feather } from '../../components/AppIcon';
import { colors, fonts, radii, spacing } from '../../theme';
import { IntegrationPlatformIcon, type IntegrationPlatform } from './IntegrationPlatformIcon';

export type IntegrationSheetTarget = {
  platform: IntegrationPlatform;
  title: string;
  subtitle: string;
};

type Props = {
  target: IntegrationSheetTarget | null;
  connectedLabel: string;
  refreshLabel: string;
  disconnectLabel: string;
  disconnectHint: string;
  cancelLabel: string;
  closeLabel: string;
  onRefresh: () => void;
  onDisconnect: () => void;
  onClose: () => void;
};

/** 3-dot Integrations menu: refresh + disconnect. No Meta reconnect row. */
export function IntegrationAccountSheet({
  target,
  connectedLabel,
  refreshLabel,
  disconnectLabel,
  disconnectHint,
  cancelLabel,
  closeLabel,
  onRefresh,
  onDisconnect,
  onClose,
}: Props) {
  const insets = useSafeAreaInsets();
  const open = target !== null;

  return (
    <AppModal visible={open} animationType="fade" onRequestClose={onClose}>
      <ModalScrim onPress={onClose} accessibilityLabel={closeLabel}>
        <Pressable
          style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, 16) + spacing.md }]}
          onPress={(e) => e.stopPropagation()}
        >
          <View style={styles.handle} />
          <Pressable
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel={closeLabel}
            style={({ pressed }) => [styles.close, pressed && styles.pressed]}
          >
            <AppIcon icon={feather('x')} size={20} color={colors.textMuted} />
          </Pressable>

          {target ? (
            <View style={styles.identity}>
              <IntegrationPlatformIcon platform={target.platform} size={48} />
              <View style={styles.identityMeta}>
                <Text style={styles.title}>{target.title}</Text>
                {target.subtitle ? <Text style={styles.subtitle}>{target.subtitle}</Text> : null}
                <View style={styles.pill}>
                  <Text style={styles.pillText}>{connectedLabel}</Text>
                </View>
              </View>
            </View>
          ) : null}

          <View style={styles.box}>
            <Pressable
              onPress={onRefresh}
              accessibilityRole="button"
              accessibilityLabel={refreshLabel}
              style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            >
              <AppIcon icon={feather('refresh-cw')} size={20} color={colors.accent} />
              <Text style={styles.rowDark}>{refreshLabel}</Text>
            </Pressable>
            <View style={styles.rowDivider} />
            <Pressable
              onPress={onDisconnect}
              accessibilityRole="button"
              accessibilityLabel={disconnectLabel}
              style={({ pressed }) => [styles.row, pressed && styles.pressed]}
            >
              <AppIcon icon={feather('log-out')} size={20} color={colors.danger} />
              <Text style={styles.rowDanger}>{disconnectLabel}</Text>
            </Pressable>
          </View>

          <Text style={styles.hint}>{disconnectHint}</Text>

          <Pressable
            onPress={onClose}
            accessibilityRole="button"
            accessibilityLabel={cancelLabel}
            style={({ pressed }) => [styles.cancel, pressed && styles.pressed]}
          >
            <Text style={styles.cancelText}>{cancelLabel}</Text>
          </Pressable>
        </Pressable>
      </ModalScrim>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    gap: spacing.md,
  },
  handle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#D4D8D8',
    marginBottom: 4,
  },
  close: {
    position: 'absolute',
    top: spacing.md,
    right: spacing.md,
    width: 36,
    height: 36,
    alignItems: 'center',
    justifyContent: 'center',
    zIndex: 2,
  },
  identity: {
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: spacing.md,
    paddingRight: 36,
    marginTop: spacing.sm,
  },
  identityMeta: { flex: 1, gap: 3 },
  title: {
    color: colors.text,
    fontFamily: fonts.bodyMedium,
    fontSize: 17,
    fontWeight: '700',
  },
  subtitle: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 13 },
  pill: {
    alignSelf: 'flex-start',
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 3,
    marginTop: 4,
    backgroundColor: colors.accentSoft,
  },
  pillText: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 12 },
  box: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: 12,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
  },
  rowDivider: { height: StyleSheet.hairlineWidth, backgroundColor: colors.border },
  rowDark: { color: colors.text, fontFamily: fonts.body, fontSize: 16 },
  rowDanger: { color: colors.danger, fontFamily: fonts.body, fontSize: 16 },
  hint: {
    color: colors.textMuted,
    fontFamily: fonts.body,
    fontSize: 13,
    paddingHorizontal: 2,
  },
  cancel: {
    borderWidth: 1.5,
    borderColor: colors.accent,
    borderRadius: 12,
    paddingVertical: 14,
    alignItems: 'center',
    marginTop: spacing.xs,
  },
  cancelText: {
    color: colors.accent,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '600',
  },
  pressed: { opacity: 0.6 },
});

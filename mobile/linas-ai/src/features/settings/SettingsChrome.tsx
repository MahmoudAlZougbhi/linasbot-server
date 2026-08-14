import type { ReactNode } from 'react';
import { Modal, Pressable, StyleSheet, Switch, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather, ion, mci, type AppIconName } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';

export const SETTINGS_ICONS = {
  name: feather('user'),
  email: feather('mail'),
  bell: feather('bell'),
  globe: feather('globe'),
  appearance: mci('circle-half-full'),
  help: mci('comment-question-outline'),
  about: feather('info'),
  terms: feather('file-text'),
  data: mci('shield-check-outline'),
  trash: feather('trash-2'),
  sun: feather('sun'),
  moon: feather('moon'),
  chevron: ion('chevron-forward'),
} as const;

type Tone = 'accent' | 'danger';

export function SettingsSection({ title, children }: { title: string; children: ReactNode }) {
  const { colors } = useTheme();
  return (
    <View style={styles.section}>
      <Text style={[styles.sectionTitle, { color: colors.textDim }]}>{title}</Text>
      <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
        {children}
      </View>
    </View>
  );
}

type RowProps = {
  icon: AppIconName;
  label: string;
  value?: string;
  hint?: string;
  tone?: Tone;
  showChevron?: boolean;
  last?: boolean;
  onPress?: () => void;
  accessory?: ReactNode;
};

export function SettingsRow({
  icon,
  label,
  value,
  hint,
  tone = 'accent',
  showChevron = true,
  last,
  onPress,
  accessory,
}: RowProps) {
  const { colors } = useTheme();
  const danger = tone === 'danger';
  const iconFg = danger ? colors.danger : colors.accent;
  const iconBg = danger ? 'rgba(220, 38, 38, 0.10)' : colors.accentSoft;
  const labelColor = danger ? colors.danger : colors.text;
  const inner = (
    <View style={styles.rowInner}>
      <View style={styles.rowText}>
        <Text style={[styles.rowLabel, { color: labelColor }]} numberOfLines={1}>
          {label}
        </Text>
        {hint ? (
          <Text style={[styles.rowHint, { color: danger ? colors.danger : colors.textMuted }]} numberOfLines={2}>
            {hint}
          </Text>
        ) : null}
      </View>
      {value ? (
        <Text style={[styles.rowValue, { color: colors.textMuted }]} numberOfLines={1}>
          {value}
        </Text>
      ) : null}
      {accessory}
      {showChevron ? <AppIcon icon={SETTINGS_ICONS.chevron} size={18} color={danger ? colors.danger : colors.textDim} /> : null}
    </View>
  );
  const rule = !last ? { borderBottomColor: colors.border, borderBottomWidth: StyleSheet.hairlineWidth } : null;
  const body = (
    <>
      <View style={[styles.iconBox, { backgroundColor: iconBg }]}>
        <AppIcon icon={icon} size={18} color={iconFg} />
      </View>
      <View style={[styles.rowMain, rule]}>{inner}</View>
    </>
  );

  if (onPress) {
    return (
      <Pressable
        style={({ pressed }) => [styles.row, pressed && styles.pressed]}
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={value ? `${label}, ${value}` : label}
      >
        {body}
      </Pressable>
    );
  }
  return <View style={styles.row}>{body}</View>;
}

export function SettingsNotifySwitch({
  value,
  onValueChange,
}: {
  value: boolean;
  onValueChange: (next: boolean) => void;
}) {
  const { colors } = useTheme();
  return (
    <Switch
      value={value}
      onValueChange={onValueChange}
      trackColor={{ false: colors.border, true: colors.accent }}
      thumbColor={colors.surface}
      ios_backgroundColor={colors.border}
      accessibilityRole="switch"
    />
  );
}

export function SettingsAppearanceToggle({
  resolved,
  onSelect,
}: {
  resolved: 'light' | 'dark';
  onSelect: (mode: 'light' | 'dark') => void;
}) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  return (
    <View style={[styles.seg, { backgroundColor: colors.input, borderColor: colors.borderSoft }]}>
      <Pressable
        style={[styles.segBtn, resolved === 'light' && { backgroundColor: colors.accentSoft }]}
        onPress={() => onSelect('light')}
        accessibilityRole="button"
        accessibilityState={{ selected: resolved === 'light' }}
        accessibilityLabel={tr('settingsAppearanceLight')}
      >
        <AppIcon icon={SETTINGS_ICONS.sun} size={14} color={resolved === 'light' ? colors.accent : colors.text} />
        <Text style={[styles.segLabel, { color: resolved === 'light' ? colors.accent : colors.text }]}>
          {tr('settingsAppearanceLight')}
        </Text>
      </Pressable>
      <Pressable
        style={[styles.segBtn, resolved === 'dark' && { backgroundColor: colors.accentSoft }]}
        onPress={() => onSelect('dark')}
        accessibilityRole="button"
        accessibilityState={{ selected: resolved === 'dark' }}
        accessibilityLabel={tr('settingsAppearanceDark')}
      >
        <AppIcon icon={SETTINGS_ICONS.moon} size={14} color={resolved === 'dark' ? colors.accent : colors.text} />
        <Text style={[styles.segLabel, { color: resolved === 'dark' ? colors.accent : colors.text }]}>
          {tr('settingsAppearanceDark')}
        </Text>
      </Pressable>
    </View>
  );
}

export function SettingsDeleteCard({ onPress }: { onPress: () => void }) {
  const { colors, resolved } = useTheme();
  const { tr } = useI18n();
  const bg = resolved === 'dark' ? 'rgba(248, 113, 113, 0.12)' : 'rgba(220, 38, 38, 0.06)';
  const border = resolved === 'dark' ? 'rgba(248, 113, 113, 0.38)' : 'rgba(248, 113, 113, 0.45)';
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={tr('settingsDeleteAccount')}
      style={({ pressed }) => [
        styles.deleteCard,
        { backgroundColor: bg, borderColor: border },
        pressed && styles.pressed,
      ]}
    >
      <View style={[styles.iconBox, { backgroundColor: 'rgba(220, 38, 38, 0.12)' }]}>
        <AppIcon icon={SETTINGS_ICONS.trash} size={18} color={colors.danger} />
      </View>
      <View style={styles.rowText}>
        <Text style={[styles.rowLabel, { color: colors.danger }]}>{tr('settingsDeleteAccount')}</Text>
        <Text style={[styles.rowHint, { color: '#C47A7A' }]}>{tr('settingsDeleteAccountSub')}</Text>
      </View>
      <AppIcon icon={SETTINGS_ICONS.chevron} size={18} color={colors.danger} />
    </Pressable>
  );
}

export function SettingsLogoutButton({ onPress }: { onPress: () => void }) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={tr('logout')}
      style={({ pressed }) => [
        styles.logout,
        { backgroundColor: colors.surface, borderColor: colors.danger },
        pressed && styles.pressed,
      ]}
    >
      <Text style={[styles.logoutLabel, { color: colors.danger }]}>{tr('logout')}</Text>
    </Pressable>
  );
}

export function SettingsFooter({ version, build }: { version: string; build: string }) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const line = tr('settingsVersionFooter').replace('{version}', version).replace('{build}', build);
  return <Text style={[styles.footer, { color: colors.textDim }]}>{line}</Text>;
}

export function SettingsSheet({
  visible,
  title,
  onClose,
  children,
}: {
  visible: boolean;
  title: string;
  onClose: () => void;
  children: ReactNode;
}) {
  const insets = useSafeAreaInsets();
  const { colors } = useTheme();
  const { tr } = useI18n();
  return (
    <Modal visible={visible} transparent animationType="slide" onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose}>
        <Pressable
          style={[
            styles.sheet,
            {
              backgroundColor: colors.surface,
              paddingBottom: Math.max(insets.bottom, 16) + spacing.md,
            },
          ]}
          onPress={(e) => e.stopPropagation()}
        >
          <View style={[styles.handle, { backgroundColor: colors.border }]} />
          <Text style={[styles.sheetTitle, { color: colors.text }]}>{title}</Text>
          {children}
          <Pressable onPress={onClose} style={styles.sheetCancel} accessibilityRole="button">
            <Text style={[styles.sheetCancelLabel, { color: colors.accent }]}>{tr('settingsAppleCancel')}</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  section: { marginBottom: spacing.lg },
  sectionTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.9,
    textTransform: 'uppercase',
    marginBottom: spacing.sm,
    marginLeft: 4,
  },
  card: {
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    overflow: 'hidden',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    paddingLeft: spacing.md,
    minHeight: 56,
  },
  iconBox: {
    width: 34,
    height: 34,
    borderRadius: 10,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowMain: { flex: 1, minWidth: 0, marginLeft: 12 },
  rowInner: {
    flexDirection: 'row',
    alignItems: 'center',
    minHeight: 56,
    paddingRight: spacing.md,
    paddingVertical: 12,
    gap: 8,
  },
  rowText: { flex: 1, minWidth: 0 },
  rowLabel: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '600' },
  rowHint: { fontFamily: fonts.body, fontSize: 12, marginTop: 2 },
  rowValue: { fontFamily: fonts.body, fontSize: 14, maxWidth: 148, textAlign: 'right' },
  pressed: { opacity: 0.62 },
  seg: {
    flexDirection: 'row',
    flexShrink: 0,
    borderRadius: 10,
    borderWidth: StyleSheet.hairlineWidth,
    padding: 3,
    gap: 3,
  },
  segBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    paddingHorizontal: 10,
    paddingVertical: 6,
    borderRadius: 8,
  },
  segLabel: { fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  deleteCard: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    borderRadius: 14,
    borderWidth: StyleSheet.hairlineWidth,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
    marginBottom: spacing.md,
  },
  logout: {
    borderRadius: 14,
    borderWidth: 1,
    minHeight: 50,
    alignItems: 'center',
    justifyContent: 'center',
    marginBottom: spacing.lg,
  },
  logoutLabel: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  footer: {
    fontFamily: fonts.body,
    fontSize: 12,
    textAlign: 'center',
    marginBottom: spacing.xxl,
  },
  scrim: { flex: 1, justifyContent: 'flex-end', backgroundColor: 'rgba(16, 34, 26, 0.42)' },
  sheet: {
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
  },
  handle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: 2,
    marginBottom: 10,
  },
  sheetTitle: { fontFamily: fonts.bodyMedium, fontSize: 18, fontWeight: '700', marginBottom: spacing.md },
  sheetCancel: { alignItems: 'center', paddingVertical: 10 },
  sheetCancelLabel: { fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
});

import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppModal } from '../../components/AppModal';
import { ModalScrim } from '../../components/ModalScrim';

import { AppIcon, feather } from '../../components/AppIcon';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, radii, spacing } from '../../theme';
import { UserOutlinedField } from './UserOutlinedField';
import type { TenantRole } from './usersRolesApi';

type Props = {
  roleId: string;
  roles: TenantRole[];
  disabled?: boolean;
  onSelect: (roleId: string) => void;
  onCreate: (name: string) => void;
  creating?: boolean;
};

const SYSTEM_LABEL: Record<string, StringKey> = {
  admin: 'roleAdmin',
  operator: 'roleOperator',
  viewer: 'roleViewer',
};

export function UserRolePicker({ roleId, roles, disabled, onSelect, onCreate, creating }: Props) {
  const { tr } = useI18n();
  const insets = useSafeAreaInsets();
  const [open, setOpen] = useState(false);
  const [creatingOpen, setCreatingOpen] = useState(false);
  const [name, setName] = useState('');
  const selected = roles.find((role) => role.id === roleId);
  const label = selected
    ? selected.system
      ? tr(SYSTEM_LABEL[selected.id] || 'roleViewer')
      : selected.name
    : tr('usersRole');

  return (
    <View>
      <Pressable
        onPress={() => !disabled && setOpen(true)}
        disabled={disabled}
        accessibilityRole="button"
        accessibilityLabel={tr('usersRole')}
      >
        <UserOutlinedField label={tr('usersRole')} value={label} editable={false} pointerEvents="none" />
        <View style={styles.chevron}>
          <AppIcon icon={feather('chevron-down')} size={18} color={colors.textMuted} />
        </View>
      </Pressable>

      <AppModal visible={open} animationType="fade" onRequestClose={() => setOpen(false)}>
        <ModalScrim onPress={() => setOpen(false)}>
          <Pressable
            style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, 16) + spacing.md }]}
            onPress={(e) => e.stopPropagation()}
          >
            <View style={styles.handle} />
            {roles.map((role) => (
              <Pressable
                key={role.id}
                onPress={() => {
                  onSelect(role.id);
                  setOpen(false);
                }}
                style={({ pressed }) => [styles.option, pressed && styles.pressed]}
              >
                <Text style={styles.optionText}>
                  {role.system ? tr(SYSTEM_LABEL[role.id] || 'roleViewer') : role.name}
                </Text>
                {role.id === roleId ? (
                  <AppIcon icon={feather('check')} size={18} color={colors.accent} />
                ) : null}
              </Pressable>
            ))}
            <Pressable
              onPress={() => {
                setOpen(false);
                setCreatingOpen(true);
              }}
              style={({ pressed }) => [styles.option, pressed && styles.pressed]}
            >
              <Text style={styles.create}>{tr('usersCreateRole')}</Text>
            </Pressable>
          </Pressable>
        </ModalScrim>
      </AppModal>

      <AppModal visible={creatingOpen} animationType="fade" onRequestClose={() => setCreatingOpen(false)}>
        <ModalScrim onPress={() => setCreatingOpen(false)} justify="center">
          <Pressable style={styles.card} onPress={(e) => e.stopPropagation()}>
            <Text style={styles.cardTitle}>{tr('usersCreateRole')}</Text>
            <Text style={styles.cardSub}>{tr('usersCreateRoleHint')}</Text>
            <UserOutlinedField
              label={tr('usersRoleName')}
              value={name}
              onChangeText={setName}
              autoCapitalize="words"
            />
            <PrimaryButton
              label={tr('usersSaveRole')}
              loading={creating}
              onPress={() => {
                const trimmed = name.trim();
                if (!trimmed) return;
                onCreate(trimmed);
                setName('');
                setCreatingOpen(false);
              }}
              style={styles.save}
            />
            <Pressable onPress={() => setCreatingOpen(false)}>
              <Text style={styles.cancel}>{tr('usersCancel')}</Text>
            </Pressable>
          </Pressable>
        </ModalScrim>
      </AppModal>
    </View>
  );
}

const styles = StyleSheet.create({
  chevron: { position: 'absolute', right: 14, top: 22 },
  sheet: {
    backgroundColor: colors.surface,
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
    backgroundColor: '#D4D8D8',
    marginBottom: 8,
  },
  option: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 14,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: colors.borderSoft,
  },
  optionText: { fontFamily: fonts.body, fontSize: 16, color: colors.text },
  create: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  card: {
    margin: 24,
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    gap: 8,
  },
  cardTitle: { fontFamily: fonts.bodyMedium, fontSize: 18, fontWeight: '700', color: colors.text },
  cardSub: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted, marginBottom: 8 },
  save: { marginTop: 12 },
  cancel: {
    textAlign: 'center',
    color: colors.accent,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    marginTop: 12,
  },
  pressed: { opacity: 0.55 },
});

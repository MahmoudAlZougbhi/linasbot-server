import { Modal, Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { UserPasswordField } from './UserPasswordField';

type Props = {
  visible: boolean;
  busy?: boolean;
  error?: string | null;
  password: string;
  onPassword: (value: string) => void;
  onSave: () => void;
  onClose: () => void;
};

export function UserResetPasswordSheet({
  visible,
  busy,
  error,
  password,
  onPassword,
  onSave,
  onClose,
}: Props) {
  const insets = useSafeAreaInsets();
  const { tr } = useI18n();
  return (
    <Modal visible={visible} transparent animationType="fade" onRequestClose={onClose}>
      <Pressable style={styles.scrim} onPress={onClose}>
        <Pressable
          style={[styles.sheet, { paddingBottom: Math.max(insets.bottom, 16) + spacing.md }]}
          onPress={(e) => e.stopPropagation()}
        >
          <View style={styles.handle} />
          <Text style={styles.title}>{tr('usersResetPassword')}</Text>
          <Text style={styles.sub}>{tr('usersResetHint')}</Text>
          <UserPasswordField value={password} onChange={onPassword} editable={!busy} />
          {error ? <Text style={styles.error}>{error}</Text> : null}
          <PrimaryButton label={tr('usersSave')} onPress={onSave} loading={busy} disabled={busy} />
          <Pressable onPress={onClose} style={styles.cancelWrap}>
            <Text style={styles.cancel}>{tr('usersCancel')}</Text>
          </Pressable>
        </Pressable>
      </Pressable>
    </Modal>
  );
}

const styles = StyleSheet.create({
  scrim: { flex: 1, justifyContent: 'flex-end', backgroundColor: colors.overlay },
  sheet: {
    backgroundColor: colors.surface,
    borderTopLeftRadius: radii.xl,
    borderTopRightRadius: radii.xl,
    paddingHorizontal: spacing.lg,
    paddingTop: spacing.sm,
    gap: spacing.sm,
  },
  handle: {
    alignSelf: 'center',
    width: 36,
    height: 4,
    borderRadius: 2,
    backgroundColor: '#D4D8D8',
    marginBottom: 8,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 18, fontWeight: '700', color: colors.text },
  sub: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted, marginBottom: 8 },
  error: { color: colors.danger, fontFamily: fonts.body, fontSize: 14 },
  cancelWrap: { alignItems: 'center', paddingVertical: 8 },
  cancel: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
});

import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { generateTempPassword } from './usersAccess';

type Props = {
  value: string;
  onChange: (next: string) => void;
  editable?: boolean;
  label?: string;
};

export function UserPasswordField({ value, onChange, editable = true, label }: Props) {
  const { tr } = useI18n();
  const [visible, setVisible] = useState(false);

  return (
    <View style={styles.wrap}>
      <View style={styles.labelHit}>
        <Text style={styles.label}>{label || tr('usersTempPassword')}</Text>
      </View>
      <View style={styles.row}>
        <View style={styles.field}>
          <TextInput
            value={value}
            onChangeText={onChange}
            secureTextEntry={!visible}
            autoCapitalize="none"
            autoCorrect={false}
            editable={editable}
            style={styles.input}
            placeholderTextColor={colors.textDim}
          />
          <Pressable
            onPress={() => setVisible((v) => !v)}
            hitSlop={8}
            accessibilityRole="button"
            accessibilityLabel={visible ? 'Hide password' : 'Show password'}
            style={({ pressed }) => [styles.eye, pressed && styles.pressed]}
          >
            <AppIcon icon={feather(visible ? 'eye-off' : 'eye')} size={20} color={colors.textMuted} />
          </Pressable>
        </View>
        <Pressable
          onPress={() => onChange(generateTempPassword())}
          disabled={!editable}
          accessibilityRole="button"
          accessibilityLabel={tr('usersGenerate')}
          style={({ pressed }) => [styles.generate, pressed && styles.pressed]}
        >
          <Text style={styles.generateText}>{tr('usersGenerate')}</Text>
        </Pressable>
      </View>
      <Text style={styles.hint}>{tr('usersPasswordHint')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { marginTop: 10 },
  labelHit: {
    position: 'absolute',
    top: -8,
    left: 12,
    zIndex: 2,
    backgroundColor: colors.surface,
    paddingHorizontal: 6,
  },
  label: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  field: {
    flex: 1,
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.md,
  },
  input: {
    flex: 1,
    fontFamily: fonts.body,
    fontSize: 16,
    color: colors.text,
    paddingHorizontal: spacing.md,
    paddingVertical: 14,
  },
  eye: { paddingHorizontal: 10, paddingVertical: 10 },
  generate: { paddingVertical: 8, paddingHorizontal: 4 },
  generateText: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  hint: { marginTop: 6, fontFamily: fonts.body, fontSize: 12, color: colors.textDim },
  pressed: { opacity: 0.55 },
});

import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import type { WebChatAppearance } from './webChatTypes';

type Props = {
  appearance: WebChatAppearance;
  contrastWarnings: string[];
  disabled?: boolean;
  onChange: (next: WebChatAppearance) => void;
};

function Chip({
  label,
  active,
  onPress,
  disabled,
}: {
  label: string;
  active: boolean;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      disabled={disabled}
      onPress={onPress}
      style={[styles.chip, active ? styles.chipOn : styles.chipOff, disabled && styles.disabled]}
    >
      <Text style={[styles.chipText, active ? styles.chipTextOn : styles.chipTextOff]}>{label}</Text>
    </Pressable>
  );
}

function Field({
  label,
  value,
  onChangeText,
  disabled,
}: {
  label: string;
  value: string;
  onChangeText: (v: string) => void;
  disabled?: boolean;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChangeText}
        editable={!disabled}
        style={styles.input}
        placeholderTextColor={colors.textMuted}
      />
    </View>
  );
}

export function WebChatWidgetCustomize({ appearance, contrastWarnings, disabled, onChange }: Props) {
  const { tr } = useI18n();

  function patch<K extends keyof WebChatAppearance>(
    section: K,
    value: Partial<WebChatAppearance[K]>,
  ) {
    onChange({
      ...appearance,
      [section]: { ...appearance[section], ...value },
    });
  }

  return (
    <View style={styles.wrap}>
      <Text style={styles.section}>{tr('webChatIdentityTitle')}</Text>
      <Field
        label={tr('webChatDisplayName')}
        value={appearance.identity.display_name}
        onChangeText={(v) => patch('identity', { display_name: v })}
        disabled={disabled}
      />
      <Field
        label={tr('webChatWelcomeMessage')}
        value={appearance.identity.welcome_message}
        onChangeText={(v) => patch('identity', { welcome_message: v })}
        disabled={disabled}
      />
      <Field
        label={tr('webChatSubtitleField')}
        value={appearance.identity.subtitle}
        onChangeText={(v) => patch('identity', { subtitle: v })}
        disabled={disabled}
      />
      <Field
        label={tr('webChatLogoUrl')}
        value={appearance.identity.logo_url}
        onChangeText={(v) => patch('identity', { logo_url: v })}
        disabled={disabled}
      />

      <Text style={styles.section}>{tr('webChatThemeTitle')}</Text>
      <View style={styles.row}>
        <Chip
          label={tr('webChatThemeLight')}
          active={appearance.theme.mode === 'light'}
          onPress={() => patch('theme', { mode: 'light' })}
          disabled={disabled}
        />
        <Chip
          label={tr('webChatThemeDark')}
          active={appearance.theme.mode === 'dark'}
          onPress={() => patch('theme', { mode: 'dark' })}
          disabled={disabled}
        />
      </View>
      <Field
        label={tr('webChatAccentColor')}
        value={appearance.theme.accent_color}
        onChangeText={(v) => patch('theme', { accent_color: v })}
        disabled={disabled}
      />

      <Text style={styles.section}>{tr('webChatBubblesTitle')}</Text>
      <Field
        label={tr('webChatAiBg')}
        value={appearance.bubbles.assistant_bg}
        onChangeText={(v) => patch('bubbles', { assistant_bg: v })}
        disabled={disabled}
      />
      <Field
        label={tr('webChatAiText')}
        value={appearance.bubbles.assistant_text}
        onChangeText={(v) => patch('bubbles', { assistant_text: v })}
        disabled={disabled}
      />
      <Field
        label={tr('webChatVisitorBg')}
        value={appearance.bubbles.visitor_bg}
        onChangeText={(v) => patch('bubbles', { visitor_bg: v })}
        disabled={disabled}
      />
      <Field
        label={tr('webChatVisitorText')}
        value={appearance.bubbles.visitor_text}
        onChangeText={(v) => patch('bubbles', { visitor_text: v })}
        disabled={disabled}
      />
      {contrastWarnings.length ? (
        <Text style={styles.warn}>{tr('webChatContrastWarn')}</Text>
      ) : null}

      <Text style={styles.section}>{tr('webChatLayoutTitle')}</Text>
      <View style={styles.row}>
        <Chip
          label={tr('webChatPositionBL')}
          active={appearance.layout.position === 'bottom_left'}
          onPress={() => patch('layout', { position: 'bottom_left' })}
          disabled={disabled}
        />
        <Chip
          label={tr('webChatPositionBR')}
          active={appearance.layout.position === 'bottom_right'}
          onPress={() => patch('layout', { position: 'bottom_right' })}
          disabled={disabled}
        />
      </View>
      <View style={styles.row}>
        {(['compact', 'standard', 'large'] as const).map((size) => (
          <Chip
            key={size}
            label={tr(size === 'compact' ? 'webChatSizeCompact' : size === 'large' ? 'webChatSizeLarge' : 'webChatSizeStandard')}
            active={appearance.layout.size === size}
            onPress={() => patch('layout', { size })}
            disabled={disabled}
          />
        ))}
      </View>
      <View style={styles.row}>
        {(['soft', 'rounded', 'extra_rounded'] as const).map((corners) => (
          <Chip
            key={corners}
            label={tr(
              corners === 'soft'
                ? 'webChatCornersSoft'
                : corners === 'extra_rounded'
                  ? 'webChatCornersExtra'
                  : 'webChatCornersRounded',
            )}
            active={appearance.layout.corners === corners}
            onPress={() => patch('layout', { corners })}
            disabled={disabled}
          />
        ))}
      </View>

      <Text style={styles.section}>{tr('webChatLauncherTitle')}</Text>
      <View style={styles.row}>
        <Chip
          label={tr('webChatLauncherIcon')}
          active={appearance.launcher.mode === 'icon'}
          onPress={() => patch('launcher', { mode: 'icon' })}
          disabled={disabled}
        />
        <Chip
          label={tr('webChatLauncherIconText')}
          active={appearance.launcher.mode === 'icon_text'}
          onPress={() => patch('launcher', { mode: 'icon_text' })}
          disabled={disabled}
        />
      </View>
      {appearance.launcher.mode === 'icon_text' ? (
        <Field
          label={tr('webChatLauncherText')}
          value={appearance.launcher.text}
          onChangeText={(v) => patch('launcher', { text: v })}
          disabled={disabled}
        />
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  section: { fontFamily: fonts.bodyMedium, fontSize: 14, color: colors.text, marginTop: spacing.xs },
  field: { gap: 4 },
  label: { fontFamily: fonts.body, fontSize: 12, color: colors.textMuted },
  input: {
    borderWidth: 1,
    borderColor: colors.border,
    borderRadius: radii.sm,
    paddingHorizontal: spacing.sm,
    paddingVertical: 8,
    fontFamily: fonts.body,
    fontSize: 14,
    color: colors.text,
  },
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: spacing.xs },
  chip: { borderRadius: 999, paddingHorizontal: 12, paddingVertical: 6, borderWidth: 1 },
  chipOn: { backgroundColor: colors.accentSoft, borderColor: colors.accent },
  chipOff: { backgroundColor: colors.input, borderColor: colors.border },
  chipText: { fontFamily: fonts.bodyMedium, fontSize: 12 },
  chipTextOn: { color: colors.accent },
  chipTextOff: { color: colors.textMuted },
  warn: { fontFamily: fonts.body, fontSize: 12, color: colors.warning },
  disabled: { opacity: 0.6 },
});

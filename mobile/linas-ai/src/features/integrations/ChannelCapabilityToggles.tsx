import { ActivityIndicator, StyleSheet, Switch, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';

export type ChannelToggles = {
  dm: boolean;
  comments: boolean;
};

type Props = {
  toggles: ChannelToggles;
  busyKey: 'dm' | 'comments' | null;
  disabled?: boolean;
  /** When true, switches stay OFF and cannot be turned on (platform disconnected). */
  lockedOff?: boolean;
  onToggle: (key: 'dm' | 'comments', value: boolean) => void;
};

export function ChannelCapabilityToggles({
  toggles,
  busyKey,
  disabled,
  lockedOff,
  onToggle,
}: Props) {
  const { tr } = useI18n();
  const forceOff = lockedOff === true;

  return (
    <View style={styles.wrap}>
      <ToggleRow
        label={tr('toggleDms')}
        value={forceOff ? false : toggles.dm}
        busy={busyKey === 'dm'}
        disabled={forceOff || disabled || busyKey !== null}
        onValueChange={(v) => onToggle('dm', v)}
      />
      <ToggleRow
        label={tr('toggleComments')}
        value={forceOff ? false : toggles.comments}
        busy={busyKey === 'comments'}
        disabled={forceOff || disabled || busyKey !== null}
        onValueChange={(v) => onToggle('comments', v)}
      />
    </View>
  );
}

function ToggleRow({
  label,
  value,
  busy,
  disabled,
  onValueChange,
}: {
  label: string;
  value: boolean;
  busy: boolean;
  disabled: boolean;
  onValueChange: (value: boolean) => void;
}) {
  return (
    <View style={styles.row}>
      <Text style={styles.label}>{label}</Text>
      {busy ? (
        <ActivityIndicator color={colors.accent} />
      ) : (
        <Switch
          value={value}
          onValueChange={onValueChange}
          disabled={disabled}
          trackColor={{ false: colors.border, true: colors.accent }}
          thumbColor={colors.surface}
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 4,
  },
  label: { color: colors.text, fontFamily: fonts.body, fontSize: 15, flex: 1, paddingRight: 12 },
});

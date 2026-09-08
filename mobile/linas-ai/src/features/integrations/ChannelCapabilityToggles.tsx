import { ActivityIndicator, StyleSheet, Switch, Text, View } from 'react-native';

import { colors, fonts } from '../../theme';

export type ChannelToggleKey = 'dm' | 'comments' | 'calls';

export type ChannelToggles = {
  dm: boolean;
  comments: boolean;
  calls?: boolean;
};

type Props = {
  toggles: ChannelToggles;
  busyKey: ChannelToggleKey | null;
  disabled?: boolean;
  showComments?: boolean;
  showCalls?: boolean;
  messagesLabel: string;
  commentsLabel: string;
  callsLabel?: string;
  onToggle: (key: ChannelToggleKey, value: boolean) => void;
};

export function ChannelCapabilityToggles({
  toggles,
  busyKey,
  disabled,
  showComments = true,
  showCalls = false,
  messagesLabel,
  commentsLabel,
  callsLabel = '',
  onToggle,
}: Props) {
  return (
    <View style={styles.wrap}>
      <ToggleRow
        label={messagesLabel}
        value={toggles.dm}
        busy={busyKey === 'dm'}
        disabled={disabled || busyKey !== null}
        onValueChange={(v) => onToggle('dm', v)}
      />
      {showComments ? (
        <ToggleRow
          label={commentsLabel}
          value={toggles.comments}
          busy={busyKey === 'comments'}
          disabled={disabled || busyKey !== null}
          onValueChange={(v) => onToggle('comments', v)}
        />
      ) : null}
      {showCalls ? (
        <ToggleRow
          label={callsLabel}
          value={Boolean(toggles.calls)}
          busy={busyKey === 'calls'}
          disabled={disabled || busyKey !== null}
          onValueChange={(v) => onToggle('calls', v)}
        />
      ) : null}
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
          trackColor={{ false: '#D5DBDB', true: colors.accent }}
          thumbColor={colors.surface}
          ios_backgroundColor="#D5DBDB"
        />
      )}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 2 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    minHeight: 44,
  },
  label: { color: colors.text, fontFamily: fonts.body, fontSize: 15 },
});

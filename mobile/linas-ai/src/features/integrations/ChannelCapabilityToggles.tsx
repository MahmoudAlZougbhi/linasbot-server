import { ActivityIndicator, StyleSheet, Switch, Text, View } from 'react-native';

import type { StringKey } from '../../i18n/locales/en';
import { colors, fonts, spacing } from '../../theme';

export type ChannelToggles = {
  dm: boolean;
  comments: boolean;
};

type Props = {
  platform: 'instagram' | 'facebook';
  toggles: ChannelToggles;
  busyKey: 'dm' | 'comments' | null;
  disabled?: boolean;
  lockedOff?: boolean;
  tr: (key: StringKey) => string;
  onToggle: (key: 'dm' | 'comments', value: boolean) => void;
};

export function ChannelCapabilityToggles({
  platform,
  toggles,
  busyKey,
  disabled,
  lockedOff,
  tr,
  onToggle,
}: Props) {
  const forceOff = lockedOff === true;
  const dmLabel =
    platform === 'facebook' ? tr('integrationMessengerReplies') : tr('integrationDmReplies');

  return (
    <View style={styles.wrap}>
      <Text style={styles.sectionTitle}>{tr('integrationConnectedFeatures')}</Text>
      <ToggleRow
        label={dmLabel}
        value={forceOff ? false : toggles.dm}
        busy={busyKey === 'dm'}
        disabled={forceOff || disabled || busyKey !== null}
        stateLabel={forceOff || !toggles.dm ? tr('integrationFeatureOff') : tr('integrationFeatureOn')}
        onValueChange={(v) => onToggle('dm', v)}
      />
      <ToggleRow
        label={tr('integrationCommentReplies')}
        value={forceOff ? false : toggles.comments}
        busy={busyKey === 'comments'}
        disabled={forceOff || disabled || busyKey !== null}
        stateLabel={
          forceOff || !toggles.comments ? tr('integrationFeatureOff') : tr('integrationFeatureOn')
        }
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
  stateLabel,
  onValueChange,
}: {
  label: string;
  value: boolean;
  busy: boolean;
  disabled: boolean;
  stateLabel: string;
  onValueChange: (value: boolean) => void;
}) {
  return (
    <View style={styles.row}>
      <View style={styles.labelWrap}>
        <Text style={styles.label}>{label}</Text>
        <Text style={[styles.state, value ? styles.stateOn : styles.stateOff]}>{stateLabel}</Text>
      </View>
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
  sectionTitle: {
    color: colors.textMuted,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingVertical: 4,
  },
  labelWrap: { flex: 1, paddingRight: 12, gap: 2 },
  label: { color: colors.text, fontFamily: fonts.body, fontSize: 15 },
  state: { fontFamily: fonts.body, fontSize: 12 },
  stateOn: { color: colors.mint },
  stateOff: { color: colors.textDim },
});

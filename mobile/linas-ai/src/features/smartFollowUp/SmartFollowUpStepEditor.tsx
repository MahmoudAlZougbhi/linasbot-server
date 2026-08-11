import { Pressable, StyleSheet, Switch, Text, TextInput, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { fonts, radii, spacing, useTheme } from '../../theme';
import {
  FOLLOW_UP_GOALS,
  formatDelayLabel,
  type FollowUpGoal,
  type SmartFollowUpStep,
} from './smartFollowUpApi';

const GOAL_KEYS: Record<FollowUpGoal, StringKey> = {
  gentle_check_in: 'sfuGoalGentleCheckIn',
  offer_more_help: 'sfuGoalOfferMoreHelp',
  politely_close: 'sfuGoalPolitelyClose',
};

type Props = {
  step: SmartFollowUpStep;
  defaultDelay: number;
  disabled?: boolean;
  onChange: (next: SmartFollowUpStep) => void;
};

export function SmartFollowUpStepEditor({ step, defaultDelay, disabled, onChange }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}>
      <View style={styles.header}>
        <Text style={[styles.title, { color: colors.text }]}>
          {tr('sfuStepLabel').replace('{n}', String(step.step_index))}
        </Text>
        <Switch
          value={step.enabled}
          onValueChange={(enabled) => onChange({ ...step, enabled })}
          disabled={disabled}
          trackColor={{ false: colors.border, true: colors.accent }}
          thumbColor={colors.surface}
          accessibilityLabel={tr('sfuStepEnabled')}
        />
      </View>

      <Text style={[styles.hint, { color: colors.textDim }]}>
        {tr('sfuDefaultDelay').replace('{delay}', formatDelayLabel(defaultDelay))}
      </Text>

      <Text style={[styles.fieldLabel, { color: colors.textMuted }]}>{tr('sfuDelayMinutes')}</Text>
      <TextInput
        value={String(step.delay_minutes)}
        onChangeText={(raw) => {
          const digits = raw.replace(/[^\d]/g, '');
          const delay_minutes = digits.length ? Math.max(1, parseInt(digits, 10)) : 1;
          onChange({ ...step, delay_minutes });
        }}
        keyboardType="number-pad"
        editable={!disabled && step.enabled}
        style={[
          styles.input,
          {
            color: colors.text,
            backgroundColor: colors.input,
            borderColor: colors.border,
            opacity: step.enabled ? 1 : 0.55,
          },
        ]}
        accessibilityLabel={tr('sfuDelayMinutes')}
      />

      <Text style={[styles.fieldLabel, { color: colors.textMuted }]}>{tr('sfuGoal')}</Text>
      <View style={styles.goals}>
        {FOLLOW_UP_GOALS.map((goal) => {
          const selected = step.goal === goal;
          return (
            <Pressable
              key={goal}
              disabled={disabled || !step.enabled}
              onPress={() => onChange({ ...step, goal })}
              style={[
                styles.goalChip,
                {
                  borderColor: selected ? colors.accent : colors.border,
                  backgroundColor: selected ? colors.accentSoft : colors.input,
                  opacity: step.enabled ? 1 : 0.55,
                },
              ]}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              accessibilityLabel={tr(GOAL_KEYS[goal])}
            >
              <Text
                style={{
                  color: selected ? colors.accentDeep : colors.text,
                  fontFamily: fonts.bodyMedium,
                  fontSize: 13,
                }}
              >
                {tr(GOAL_KEYS[goal])}
              </Text>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  hint: { fontFamily: fonts.body, fontSize: 12 },
  fieldLabel: { fontFamily: fonts.bodyMedium, fontSize: 13, marginTop: 4 },
  input: {
    borderWidth: 1,
    borderRadius: radii.sm,
    paddingHorizontal: 12,
    paddingVertical: 10,
    fontSize: 15,
    fontFamily: fonts.body,
  },
  goals: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  goalChip: {
    borderWidth: 1,
    borderRadius: radii.pill,
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
});

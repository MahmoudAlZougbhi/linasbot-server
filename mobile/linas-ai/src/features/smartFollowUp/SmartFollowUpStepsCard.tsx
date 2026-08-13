import { StyleSheet, Switch, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import type { SmartFollowUpStep } from './smartFollowUpApi';
import { SmartFollowUpDropdown } from './SmartFollowUpDropdown';
import {
  GOAL_OPTIONS,
  delayOptionsForValue,
  formatDelayOptionLabel,
} from './smartFollowUpOptions';
import { SFU_CARD_BORDER, SFU_STEP_BADGE_BG, SFU_TEAL } from './smartFollowUpDesign';

type Props = {
  steps: SmartFollowUpStep[];
  disabled?: boolean;
  onChange: (step: SmartFollowUpStep) => void;
};

export function SmartFollowUpStepsCard({ steps, disabled, onChange }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View style={[styles.card, { backgroundColor: colors.surface, borderColor: SFU_CARD_BORDER }]}>
      {steps.map((step, index) => {
        const delayOptions = delayOptionsForValue(step.delay_minutes).map((o) => ({
          value: String(o.minutes),
          label: o.label,
        }));
        const goalOptions = GOAL_OPTIONS.map((g) => ({
          value: g.value,
          label: tr(g.labelKey),
        }));
        const stepDisabled = disabled || !step.enabled;

        return (
          <View
            key={step.step_index}
            style={[styles.row, index > 0 && styles.rowBorder, { borderTopColor: SFU_CARD_BORDER }]}
          >
            <View style={[styles.badge, { backgroundColor: SFU_STEP_BADGE_BG }]}>
              <Text style={[styles.badgeText, { color: colors.textMuted }]}>{step.step_index}</Text>
            </View>

            <SmartFollowUpDropdown
              value={String(step.delay_minutes)}
              options={delayOptions}
              disabled={stepDisabled}
              accessibilityLabel={tr('sfuDelayMinutes')}
              onChange={(raw) => {
                const delay_minutes = Math.max(1, parseInt(raw, 10) || 1);
                onChange({ ...step, delay_minutes });
              }}
            />

            <SmartFollowUpDropdown
              value={step.goal}
              options={goalOptions}
              disabled={stepDisabled}
              accessibilityLabel={tr('sfuGoal')}
              onChange={(goal) => onChange({ ...step, goal: goal as SmartFollowUpStep['goal'] })}
            />

            <Switch
              value={step.enabled}
              onValueChange={(enabled) => onChange({ ...step, enabled })}
              disabled={disabled}
              trackColor={{ false: colors.border, true: SFU_TEAL }}
              thumbColor={colors.surface}
              accessibilityLabel={tr('sfuStepEnabled')}
            />
          </View>
        );
      })}

      {steps.some((s) => s.enabled) ? (
        <Text style={[styles.hint, { color: colors.textMuted }]}>
          {steps
            .filter((s) => s.enabled)
            .map(
              (s) =>
                `${tr('sfuStepLabel').replace('{n}', String(s.step_index))}: ${formatDelayOptionLabel(s.delay_minutes)}`,
            )
            .join(' · ')}
        </Text>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: radii.md,
    paddingHorizontal: spacing.md,
    paddingVertical: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    paddingVertical: spacing.sm,
  },
  rowBorder: {
    borderTopWidth: StyleSheet.hairlineWidth,
  },
  badge: {
    width: 24,
    height: 24,
    borderRadius: 12,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: {
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
  },
  hint: {
    fontFamily: fonts.body,
    fontSize: 12,
    paddingBottom: spacing.xs,
  },
});

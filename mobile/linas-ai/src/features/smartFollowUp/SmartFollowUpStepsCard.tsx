import { StyleSheet, Switch, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import type { SmartFollowUpStep } from './smartFollowUpApi';
import { SmartFollowUpDropdown } from './SmartFollowUpDropdown';
import { GOAL_OPTIONS, delayOptionsForValue } from './smartFollowUpOptions';
import {
  SFU_CARD_BORDER,
  SFU_STEP_BADGE_BG,
  SFU_STEP_RADIUS,
  SFU_TEAL,
} from './smartFollowUpDesign';

type Props = {
  steps: SmartFollowUpStep[];
  disabled?: boolean;
  onChange: (step: SmartFollowUpStep) => void;
};

export function SmartFollowUpStepsCard({ steps, disabled, onChange }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View
      style={[
        styles.card,
        { backgroundColor: colors.surface, borderColor: SFU_CARD_BORDER },
      ]}
    >
      <Text style={[styles.title, { color: colors.text }]}>{tr('sfuStepsTitle')}</Text>

      {steps.map((step) => {
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
          <View key={step.step_index}>
            <View style={[styles.hairline, { backgroundColor: SFU_CARD_BORDER }]} />
            <View style={styles.row}>
              <View style={[styles.badge, { backgroundColor: SFU_STEP_BADGE_BG }]}>
                <Text style={[styles.badgeText, { color: colors.text }]}>{step.step_index}</Text>
              </View>

              <SmartFollowUpDropdown
                value={String(step.delay_minutes)}
                options={delayOptions}
                disabled={stepDisabled}
                flex={0.82}
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
                flex={1.28}
                accessibilityLabel={tr('sfuGoal')}
                onChange={(goal) => onChange({ ...step, goal: goal as SmartFollowUpStep['goal'] })}
              />

              <Switch
                value={step.enabled}
                onValueChange={(enabled) => onChange({ ...step, enabled })}
                disabled={disabled}
                trackColor={{ false: colors.border, true: SFU_TEAL }}
                thumbColor="#FFFFFF"
                ios_backgroundColor={colors.border}
                accessibilityLabel={tr('sfuStepEnabled')}
              />
            </View>
          </View>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderWidth: 1,
    borderRadius: SFU_STEP_RADIUS,
    overflow: 'hidden',
    paddingTop: spacing.lg,
  },
  title: {
    fontFamily: fonts.display,
    fontSize: 16,
    paddingHorizontal: spacing.lg,
    paddingBottom: spacing.md,
  },
  hairline: {
    height: StyleSheet.hairlineWidth,
    alignSelf: 'stretch',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: spacing.lg,
    paddingVertical: 14,
  },
  badge: {
    width: 28,
    height: 28,
    borderRadius: 14,
    alignItems: 'center',
    justifyContent: 'center',
  },
  badgeText: {
    fontFamily: fonts.display,
    fontSize: 13,
  },
});

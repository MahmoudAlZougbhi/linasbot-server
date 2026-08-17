/** Two-step Products wizard stepper. */

import { StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { fonts } from '../../theme';
import { PR_BORDER, PR_MUTED, PR_TEAL } from './productChrome';

type Props = {
  step: 1 | 2;
  detailsLabel: string;
  mediaLabel: string;
};

export function ProductStepper({ step, detailsLabel, mediaLabel }: Props) {
  const step1Done = step > 1;
  return (
    <View style={styles.wrap}>
      <StepDot
        active={step === 1 || step1Done}
        done={step1Done}
        index={1}
        label={detailsLabel}
      />
      <View style={[styles.line, step1Done && styles.lineOn]} />
      <StepDot active={step === 2} done={false} index={2} label={mediaLabel} />
    </View>
  );
}

function StepDot({
  active,
  done,
  index,
  label,
}: {
  active: boolean;
  done: boolean;
  index: number;
  label: string;
}) {
  return (
    <View style={styles.step}>
      <View style={[styles.circle, active && styles.circleOn]}>
        {done ? (
          <AppIcon icon={feather('check')} size={14} color="#FFFFFF" />
        ) : (
          <Text style={[styles.num, active && styles.numOn]}>{index}</Text>
        )}
      </View>
      <Text style={[styles.label, active && styles.labelOn]} numberOfLines={1}>
        {label}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 4 },
  step: { flexDirection: 'row', alignItems: 'center', gap: 8, flexShrink: 1 },
  circle: {
    width: 28,
    height: 28,
    borderRadius: 14,
    borderWidth: 1.5,
    borderColor: PR_BORDER,
    alignItems: 'center',
    justifyContent: 'center',
    backgroundColor: '#FFFFFF',
  },
  circleOn: { backgroundColor: PR_TEAL, borderColor: PR_TEAL },
  num: { color: PR_MUTED, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
  numOn: { color: '#FFFFFF' },
  label: { color: PR_MUTED, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  labelOn: { color: PR_TEAL },
  line: { flex: 1, height: 2, backgroundColor: PR_BORDER, borderRadius: 1 },
  lineOn: { backgroundColor: PR_TEAL },
});

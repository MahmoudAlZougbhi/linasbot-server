import { StyleSheet, Text, TextInput, View } from 'react-native';

import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { ClampedLongField } from '../ClampedLongField';
import { AB_BORDER, AB_MUTED, AB_RADIUS, AB_TEXT } from './aiBasicsChrome';

type Props = {
  payload: Record<string, unknown>;
  onChange: (next: Record<string, unknown>) => void;
  tr: (key: StringKey) => string;
};

function str(payload: Record<string, unknown>, key: string): string {
  const v = payload[key];
  return typeof v === 'string' ? v : v == null ? '' : String(v);
}

export function AiBasicsIdentityTab({ payload, onChange, tr }: Props) {
  const set = (key: string, value: string) => onChange({ ...payload, [key]: value });

  return (
    <View style={styles.wrap}>
      <Text style={styles.section}>{tr('aiSetupBasicsIdentityHeading')}</Text>
      <LabeledInput
        label={tr('aiSetupBusinessName')}
        value={str(payload, 'clinic_name')}
        onChange={(v) => set('clinic_name', v)}
      />
      <LabeledInput
        label={tr('aiSetupAiName')}
        value={str(payload, 'assistant_name')}
        onChange={(v) => set('assistant_name', v)}
      />
      <LabeledInput
        label={tr('aiSetupAiRole')}
        value={str(payload, 'ai_role')}
        onChange={(v) => set('ai_role', v)}
        placeholder={tr('aiSetupAiRolePlaceholder')}
      />

      <Text style={[styles.section, styles.sectionGap]}>{tr('aiSetupBasicsPurposeHeading')}</Text>
      <ClampedLongField
        label={tr('aiSetupBusinessPurpose')}
        value={str(payload, 'business_purpose')}
        onChange={(v) => set('business_purpose', v)}
        placeholder={tr('aiSetupBusinessPurposePlaceholder')}
        labelStyle={styles.label}
        inputStyle={styles.area}
        placeholderTextColor={AB_MUTED}
      />
      <ClampedLongField
        label={tr('aiSetupShortIntro')}
        value={str(payload, 'short_introduction')}
        onChange={(v) => set('short_introduction', v)}
        labelStyle={styles.label}
        inputStyle={styles.area}
        placeholderTextColor={AB_MUTED}
      />
    </View>
  );
}

function LabeledInput({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{label}</Text>
      <TextInput
        value={value}
        onChangeText={onChange}
        placeholder={placeholder}
        placeholderTextColor={AB_MUTED}
        style={styles.input}
      />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 4, paddingBottom: 12 },
  section: {
    color: AB_TEXT,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '700',
    marginBottom: 8,
  },
  sectionGap: { marginTop: 16 },
  field: { marginBottom: 10 },
  label: {
    color: AB_TEXT,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 6,
  },
  input: {
    borderWidth: 1,
    borderColor: AB_BORDER,
    borderRadius: AB_RADIUS,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: AB_TEXT,
    fontFamily: fonts.body,
    fontSize: 15,
  },
  area: {
    borderWidth: 1,
    borderColor: AB_BORDER,
    borderRadius: AB_RADIUS,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    paddingVertical: 12,
    color: AB_TEXT,
    fontFamily: fonts.body,
    fontSize: 15,
    minHeight: 96,
  },
});

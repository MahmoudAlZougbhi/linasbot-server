import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { Field } from '../cm/editors/Field';
import type { ServiceOptionInput } from './servicesApi';

type Props = {
  index: number;
  option: ServiceOptionInput;
  onChange: (next: ServiceOptionInput) => void;
  onRemove?: () => void;
  canRemove: boolean;
};

export function ServiceOptionRow({ index, option, onChange, onRemove, canRemove }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();

  return (
    <View style={styles.group}>
      <View style={styles.header}>
        <Text style={styles.groupLabel}>{`${tr('servicesOption')} ${index + 1}`}</Text>
        {canRemove && onRemove ? (
          <Pressable onPress={onRemove} accessibilityRole="button">
            <Text style={{ color: colors.danger, fontSize: 12 }}>{tr('servicesRemoveOption')}</Text>
          </Pressable>
        ) : null}
      </View>
      <View style={styles.fields}>
        <Field
          value={option.machine_name ?? ''}
          onChange={(value) => onChange({ ...option, machine_name: value })}
          placeholder={tr('servicesMachinePlaceholder')}
        />
        <Field
          value={option.body_part ?? ''}
          onChange={(value) => onChange({ ...option, body_part: value })}
          placeholder={tr('servicesBodyPartPlaceholder')}
        />
        <Field
          value={option.staff_name ?? ''}
          onChange={(value) => onChange({ ...option, staff_name: value })}
          placeholder={tr('servicesStaffPlaceholder')}
        />
        <Field
          label={tr('servicesPrice')}
          value={option.price}
          onChange={(value) => onChange({ ...option, price: value })}
          placeholder={tr('servicesPricePlaceholder')}
        />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  group: {
    borderWidth: 1,
    borderColor: '#C5D4CC',
    borderRadius: radii.md,
    backgroundColor: '#F7FAF8',
    padding: spacing.md,
    gap: spacing.sm,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  groupLabel: {
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    color: '#4A5C54',
    textTransform: 'uppercase',
    letterSpacing: 0.4,
  },
  fields: {
    gap: spacing.xs,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#D8E2DC',
    paddingTop: spacing.sm,
  },
});

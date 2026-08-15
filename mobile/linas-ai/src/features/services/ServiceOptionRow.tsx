import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
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
    <View style={styles.block}>
      <View style={styles.header}>
        <Text style={styles.rowTitle}>{`${tr('servicesOption')} ${index + 1}`}</Text>
        {canRemove && onRemove ? (
          <Pressable onPress={onRemove} accessibilityRole="button">
            <Text style={{ color: colors.danger, fontSize: 12 }}>{tr('servicesRemoveOption')}</Text>
          </Pressable>
        ) : null}
      </View>
      <Field
        label={tr('servicesMachineOptional')}
        value={option.machine_name ?? ''}
        onChange={(value) => onChange({ ...option, machine_name: value })}
        placeholder={tr('servicesMachinePlaceholder')}
      />
      <Field
        label={tr('servicesBodyPartOptional')}
        value={option.body_part ?? ''}
        onChange={(value) => onChange({ ...option, body_part: value })}
        placeholder={tr('servicesBodyPartPlaceholder')}
      />
      <Field
        label={tr('servicesStaffOptional')}
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
  );
}

const styles = StyleSheet.create({
  block: {
    gap: spacing.xs,
    paddingVertical: spacing.sm,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: '#D8E2DC',
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.xs,
  },
  rowTitle: {
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    color: '#4A5C54',
  },
});

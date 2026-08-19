import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { Field } from '../cm/editors/Field';
import {
  PR_BORDER,
  PR_INK,
  PR_MUTED,
  PR_RADIUS_SM,
  PR_TEAL,
} from './productChrome';

type Props = {
  name: string;
  description: string;
  price: string;
  sizesText: string;
  colorsText: string;
  note: string;
  availability: 'in_stock' | 'out_of_stock';
  onChangeName: (v: string) => void;
  onChangeDescription: (v: string) => void;
  onChangePrice: (v: string) => void;
  onChangeSizes: (v: string) => void;
  onChangeColors: (v: string) => void;
  onChangeNote: (v: string) => void;
  onChangeAvailability: (v: 'in_stock' | 'out_of_stock') => void;
  onContinue: () => void;
  tr: (key: StringKey) => string;
};

export function ProductDetailsStep({
  name,
  description,
  price,
  sizesText,
  colorsText,
  note,
  availability,
  onChangeName,
  onChangeDescription,
  onChangePrice,
  onChangeSizes,
  onChangeColors,
  onChangeNote,
  onChangeAvailability,
  onContinue,
  tr,
}: Props) {
  return (
    <View style={styles.wrap}>
      <Field
        label={tr('productsName')}
        value={name}
        onChange={onChangeName}
        placeholder={tr('productsNamePlaceholder')}
      />
      <Field
        label={tr('productsDescription')}
        value={description}
        onChange={onChangeDescription}
        multiline
        placeholder={tr('productsDescriptionPlaceholder')}
        hint={tr('productsDescriptionHint')}
      />
      <Text style={styles.label}>{tr('productsPrice')}</Text>
      <View style={styles.priceRow}>
        <Text style={styles.dollar}>$</Text>
        <TextInput
          value={price}
          onChangeText={onChangePrice}
          placeholder="0.00"
          placeholderTextColor={PR_MUTED}
          keyboardType="decimal-pad"
          style={styles.priceInput}
          accessibilityLabel={tr('productsPrice')}
        />
      </View>
      <Field
        label={tr('productsSizes')}
        value={sizesText}
        onChange={onChangeSizes}
        multiline
        placeholder={tr('productsSizesPlaceholder')}
        hint={tr('productsSizesHint')}
      />
      <Field
        label={tr('productsColors')}
        value={colorsText}
        onChange={onChangeColors}
        placeholder={tr('productsColorsPlaceholder')}
        hint={tr('productsColorsHint')}
      />
      <Field
        label={tr('productsNote')}
        value={note}
        onChange={onChangeNote}
        multiline
        placeholder={tr('productsNotePlaceholder')}
      />

      <Text style={styles.label}>{tr('productsAvailabilitySection')}</Text>
      <View style={styles.seg}>
        {([
          ['in_stock', tr('productsAvailability_in_stock')],
          ['out_of_stock', tr('productsAvailability_out_of_stock')],
        ] as const).map(([value, label]) => {
          const on = availability === value;
          return (
            <Pressable
              key={value}
              onPress={() => onChangeAvailability(value)}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
              style={[styles.segChip, on && styles.segChipOn]}
            >
              <Text style={[styles.segText, on && styles.segTextOn]}>{label}</Text>
            </Pressable>
          );
        })}
      </View>

      <Pressable
        onPress={onContinue}
        accessibilityRole="button"
        style={({ pressed }) => [styles.continue, pressed && styles.pressed]}
      >
        <Text style={styles.continueText}>{tr('productsContinue')}</Text>
      </Pressable>
      <Text style={styles.nextHint}>{tr('productsContinueHint')}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 4, paddingBottom: 24 },
  label: {
    color: PR_INK,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '700',
    marginBottom: 6,
    marginTop: 4,
  },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    borderWidth: 1,
    borderColor: PR_BORDER,
    borderRadius: PR_RADIUS_SM,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 14,
    minHeight: 48,
    marginBottom: 12,
    gap: 6,
  },
  dollar: { color: PR_MUTED, fontFamily: fonts.bodyMedium, fontSize: 16 },
  priceInput: {
    flex: 1,
    color: PR_INK,
    fontFamily: fonts.body,
    fontSize: 16,
    paddingVertical: 10,
    padding: 0,
  },
  seg: {
    flexDirection: 'row',
    borderWidth: 1,
    borderColor: PR_BORDER,
    borderRadius: PR_RADIUS_SM,
    overflow: 'hidden',
    marginBottom: 16,
    backgroundColor: '#FFFFFF',
  },
  segChip: {
    flex: 1,
    minHeight: 44,
    alignItems: 'center',
    justifyContent: 'center',
    paddingHorizontal: 8,
  },
  segChipOn: { backgroundColor: PR_TEAL },
  segText: { color: PR_INK, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '600' },
  segTextOn: { color: '#FFFFFF' },
  continue: {
    backgroundColor: PR_TEAL,
    borderRadius: 999,
    minHeight: 50,
    alignItems: 'center',
    justifyContent: 'center',
  },
  continueText: { color: '#FFFFFF', fontFamily: fonts.bodyMedium, fontSize: 16, fontWeight: '700' },
  nextHint: {
    color: PR_MUTED,
    fontFamily: fonts.body,
    fontSize: 13,
    textAlign: 'center',
    marginTop: 10,
  },
  pressed: { opacity: 0.75 },
});

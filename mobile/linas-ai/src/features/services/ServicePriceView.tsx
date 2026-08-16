import { Alert, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { SV_BORDER, SV_MUTED, SV_RADIUS, SV_RADIUS_SM, SV_TEAL, SV_TEAL_DARK, SV_TEAL_SOFT } from './serviceChrome';
import type { PriceDraft, ServiceDetail } from './serviceModel';

type Props = {
  draft: PriceDraft;
  error: string | null;
  canDelete: boolean;
  onTitle: (value: string) => void;
  onAmount: (value: string) => void;
  onDetails: (details: ServiceDetail[]) => void;
  onDelete: () => void;
  tr: (key: StringKey) => string;
};

export function ServicePriceView({
  draft,
  error,
  canDelete,
  onTitle,
  onAmount,
  onDetails,
  onDelete,
  tr,
}: Props) {
  const patchDetail = (index: number, patch: Partial<ServiceDetail>) => {
    onDetails(draft.details.map((row, i) => (i === index ? { ...row, ...patch } : row)));
  };

  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{tr('servicesPriceTitle')}</Text>
      <TextInput
        value={draft.title}
        onChangeText={onTitle}
        style={styles.input}
        placeholder={tr('servicesPriceTitlePlaceholder')}
        placeholderTextColor={SV_MUTED}
      />

      <Text style={styles.label}>{tr('servicesPriceDetails')}</Text>
      <Text style={styles.hint}>{tr('servicesPriceDetailsHint')}</Text>
      <View style={styles.grid}>
        <View style={styles.head}>
          <Text style={[styles.headText, styles.col]}>{tr('servicesDetail')}</Text>
          <Text style={[styles.headText, styles.col]}>{tr('servicesValue')}</Text>
          <View style={styles.minusSpace} />
        </View>
        {draft.details.map((row, index) => (
          <View key={`d-${index}`} style={styles.detailRow}>
            <TextInput
              value={row.key}
              onChangeText={(value) => patchDetail(index, { key: value })}
              style={[styles.input, styles.colInput]}
              placeholder={index === 1 ? tr('servicesDetailPlaceholder2') : tr('servicesDetailPlaceholder')}
              placeholderTextColor={SV_MUTED}
            />
            <TextInput
              value={row.value}
              onChangeText={(value) => patchDetail(index, { value })}
              style={[styles.input, styles.colInput]}
              placeholder={index === 1 ? tr('servicesValuePlaceholder2') : tr('servicesValuePlaceholder')}
              placeholderTextColor={SV_MUTED}
            />
            <Pressable
              onPress={() => onDetails(draft.details.filter((_, i) => i !== index))}
              accessibilityRole="button"
              accessibilityLabel={tr('servicesRemove')}
              style={styles.minus}
            >
              <AppIcon icon={feather('minus')} size={16} color="#FFFFFF" />
            </Pressable>
          </View>
        ))}
        <Pressable
          onPress={() => onDetails([...draft.details, { key: '', value: '' }])}
          accessibilityRole="button"
          accessibilityLabel={tr('servicesAddDetail')}
          style={({ pressed }) => [styles.outlineBtn, pressed && styles.pressed]}
        >
          <Text style={styles.outlineText}>{tr('servicesAddDetail')}</Text>
        </Pressable>
      </View>

      <Text style={styles.label}>{tr('servicesPrice')}</Text>
      <View style={styles.amountBox}>
        <Text style={styles.dollar}>$</Text>
        <TextInput
          value={draft.amountText}
          onChangeText={onAmount}
          style={styles.amountInput}
          keyboardType="decimal-pad"
          placeholder="0"
          placeholderTextColor={SV_MUTED}
        />
      </View>

      <View style={styles.info}>
        <LinasSparkleIcon size={16} color={SV_TEAL} />
        <Text style={styles.infoText}>{tr('servicesPriceHelp')}</Text>
      </View>

      {error ? <Text style={styles.error}>{error}</Text> : null}
      {canDelete ? (
        <Pressable
          onPress={() =>
            Alert.alert(tr('servicesRemovePriceTitle'), tr('servicesRemovePriceBody'), [
              { text: tr('usersCancel'), style: 'cancel' },
              { text: tr('servicesRemove'), style: 'destructive', onPress: onDelete },
            ])
          }
          style={styles.deleteLink}
        >
          <Text style={styles.deleteText}>{tr('servicesRemovePrice')}</Text>
        </Pressable>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8, paddingBottom: 16 },
  label: {
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
    marginTop: 10,
  },
  hint: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 13, marginBottom: 4 },
  input: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: SV_BORDER,
    borderRadius: SV_RADIUS_SM,
    paddingHorizontal: 12,
    paddingVertical: 12,
    color: SV_TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 15,
  },
  grid: {
    borderWidth: 1,
    borderColor: SV_BORDER,
    borderRadius: SV_RADIUS,
    padding: 12,
    gap: 10,
    backgroundColor: '#FFFFFF',
  },
  head: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  headText: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 12 },
  col: { flex: 1 },
  detailRow: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  colInput: { flex: 1, margin: 0, paddingVertical: 10 },
  minusSpace: { width: 32 },
  minus: {
    width: 32,
    height: 32,
    borderRadius: 16,
    backgroundColor: SV_TEAL,
    alignItems: 'center',
    justifyContent: 'center',
  },
  outlineBtn: {
    borderWidth: 1.5,
    borderColor: SV_TEAL,
    borderRadius: SV_RADIUS,
    paddingVertical: 11,
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
  },
  outlineText: {
    color: SV_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
  },
  amountBox: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: SV_BORDER,
    borderRadius: SV_RADIUS_SM,
    paddingHorizontal: 14,
    minHeight: 56,
  },
  dollar: {
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 22,
    fontWeight: '700',
    marginRight: 8,
  },
  amountInput: {
    flex: 1,
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 22,
    fontWeight: '700',
    paddingVertical: 12,
  },
  info: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    backgroundColor: SV_TEAL_SOFT,
    borderRadius: SV_RADIUS,
    padding: 12,
    marginTop: 8,
  },
  infoText: { color: SV_TEAL_DARK, fontFamily: fonts.body, fontSize: 13, flex: 1, lineHeight: 18 },
  error: { color: '#DC2626', fontFamily: fonts.body, fontSize: 13 },
  deleteLink: { alignItems: 'center', paddingVertical: 8 },
  deleteText: { color: '#DC2626', fontFamily: fonts.bodyMedium, fontSize: 14 },
  pressed: { opacity: 0.7 },
});

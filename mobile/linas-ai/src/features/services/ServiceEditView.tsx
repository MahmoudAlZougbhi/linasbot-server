import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { AiSetupDeletableRow } from '../cm/AiSetupDeletableRow';
import { ClampedLongField } from '../cm/ClampedLongField';
import { ServiceMediaGrid, ServiceMediaRows } from './ServiceMediaBlock';
import { SV_BORDER, SV_MUTED, SV_RADIUS, SV_RADIUS_SM, SV_TEAL, SV_TEAL_DARK, SV_TEAL_SOFT } from './serviceChrome';
import { formatMoney, type ServiceAttachment, type ServiceItem, type ServiceKind, type ServicePrice } from './serviceModel';

type Props = {
  item: ServiceItem;
  uploading: boolean;
  uploadError: string | null;
  onName: (value: string) => void;
  onNote: (value: string) => void;
  onAddPrice: () => void;
  onEditPrice: (id: string) => void;
  onDeletePrice: (id: string) => void;
  onAddResource: (kind: ServiceKind) => void;
  onRemoveResource: (id: string) => void;
  onReplaceResource: (att: ServiceAttachment) => void;
  onEditCaption: (att: ServiceAttachment) => void;
  tr: (key: StringKey) => string;
};

export function ServiceEditView({
  item,
  uploading,
  uploadError,
  onName,
  onNote,
  onAddPrice,
  onEditPrice,
  onDeletePrice,
  onAddResource,
  onRemoveResource,
  onReplaceResource,
  onEditCaption,
  tr,
}: Props) {
  return (
    <View style={styles.wrap}>
      <Text style={styles.label}>{tr('servicesName')}</Text>
      <TextInput
        value={item.name}
        onChangeText={onName}
        style={styles.input}
        placeholder={tr('servicesName')}
        placeholderTextColor={SV_MUTED}
      />

      <ClampedLongField
        label={tr('servicesNote')}
        value={item.note}
        onChange={onNote}
        placeholder={tr('servicesNotePlaceholder')}
        placeholderTextColor={SV_MUTED}
        labelStyle={styles.label}
        inputStyle={styles.input}
      />

      <Text style={styles.section}>{tr('servicesPricingSection')}</Text>
      <Text style={styles.hint}>{tr('servicesPricingHint')}</Text>
      {item.prices.length ? (
        <View style={styles.priceCard}>
          {item.prices.map((price, index) => (
            <AiSetupDeletableRow
              key={price.id}
              deleteLabel={tr('servicesRemove')}
              onRequestDelete={() => onDeletePrice(price.id)}
            >
              <PriceRow
                price={price}
                last={index === item.prices.length - 1}
                onEdit={() => onEditPrice(price.id)}
                onLongPress={() => onDeletePrice(price.id)}
              />
            </AiSetupDeletableRow>
          ))}
        </View>
      ) : null}
      <Pressable
        onPress={onAddPrice}
        accessibilityRole="button"
        accessibilityLabel={tr('servicesAddPriceOption')}
        style={({ pressed }) => [styles.outlineBtn, pressed && styles.pressed]}
      >
        <Text style={styles.outlineText}>{tr('servicesAddPriceOption')}</Text>
      </Pressable>

      <Text style={styles.section}>{tr('servicesMediaSection')}</Text>
      <Text style={styles.hint}>{tr('servicesMediaHint')}</Text>
      <ServiceMediaGrid count={item.attachments.length} disabled={uploading} onAdd={onAddResource} tr={tr} />
      {uploading ? <ActivityIndicator color={SV_TEAL} style={styles.upload} /> : null}
      {uploadError ? <Text style={styles.error}>{uploadError}</Text> : null}
      <ServiceMediaRows
        attachments={item.attachments}
        onRemove={onRemoveResource}
        onReplace={onReplaceResource}
        onEditCaption={onEditCaption}
        tr={tr}
      />
    </View>
  );
}

function PriceRow({
  price,
  last,
  onEdit,
  onLongPress,
}: {
  price: ServicePrice;
  last: boolean;
  onEdit: () => void;
  onLongPress?: () => void;
}) {
  return (
    <Pressable
      onLongPress={onLongPress}
      delayLongPress={380}
      style={[styles.priceRow, !last && styles.priceRowBorder]}
    >
      <View style={styles.priceIcon}>
        <AppIcon icon={feather('tag')} size={16} color={SV_TEAL} />
      </View>
      <View style={styles.priceCopy}>
        <Text style={styles.priceTitle} numberOfLines={1}>
          {price.title || formatMoney(price.amount, price.currency)}
        </Text>
        {price.subtitle ? <Text style={styles.priceSub}>{price.subtitle}</Text> : null}
      </View>
      <Text style={styles.priceAmt}>{formatMoney(price.amount, price.currency)}</Text>
      <Pressable onPress={onEdit} accessibilityRole="button" style={styles.pencil}>
        <AppIcon icon={feather('edit-2')} size={16} color={SV_TEAL} />
      </Pressable>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 8, paddingBottom: 16 },
  label: {
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '600',
    marginTop: 8,
  },
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
  section: {
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '700',
    marginTop: 14,
  },
  hint: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 13, marginBottom: 4 },
  priceCard: {
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: SV_BORDER,
    borderRadius: SV_RADIUS,
    overflow: 'hidden',
  },
  priceRow: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    paddingHorizontal: 12,
    paddingVertical: 12,
  },
  priceRowBorder: { borderBottomWidth: StyleSheet.hairlineWidth, borderBottomColor: SV_BORDER },
  priceIcon: {
    width: 36,
    height: 36,
    borderRadius: SV_RADIUS_SM,
    backgroundColor: SV_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  priceCopy: { flex: 1, gap: 2 },
  priceTitle: {
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
  },
  priceSub: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 12 },
  priceAmt: {
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
  },
  pencil: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  outlineBtn: {
    borderWidth: 1.5,
    borderColor: SV_TEAL,
    borderRadius: SV_RADIUS,
    paddingVertical: 12,
    alignItems: 'center',
    backgroundColor: '#FFFFFF',
  },
  outlineText: {
    color: SV_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
  },
  upload: { marginVertical: 8 },
  error: { color: '#DC2626', fontFamily: fonts.body, fontSize: 13 },
  pressed: { opacity: 0.7 },
});

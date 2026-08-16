import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { SV_BORDER, SV_MUTED, SV_RADIUS, SV_RADIUS_SM, SV_TEAL, SV_TEAL_DARK, SV_TEAL_SOFT } from './serviceChrome';
import { type ServiceAttachment, type ServiceKind } from './serviceModel';

type GridProps = {
  count: number;
  onAdd: (kind: ServiceKind) => void;
  disabled?: boolean;
  tr: (key: StringKey) => string;
};

export function ServiceMediaGrid({ count, onAdd, disabled, tr }: GridProps) {
  return (
    <View>
      <View style={styles.grid}>
        <MediaTile label={tr('servicesAddImage')} icon={feather('image')} disabled={disabled} onPress={() => onAdd('image')} />
        <MediaTile label={tr('servicesAddVideo')} icon={feather('play-circle')} disabled={disabled} onPress={() => onAdd('video')} />
        <MediaTile label={tr('servicesAddFile')} icon={feather('file')} disabled={disabled} onPress={() => onAdd('file')} />
        <MediaTile label={tr('servicesAddLink')} icon={feather('link')} disabled={disabled} onPress={() => onAdd('link')} />
      </View>
      <View style={styles.countRow}>
        <AppIcon icon={feather('paperclip')} size={14} color={SV_MUTED} />
        <Text style={styles.count}>{tr('servicesItemsAdded').replace('{count}', String(count))}</Text>
      </View>
    </View>
  );
}

function MediaTile({
  label,
  icon,
  onPress,
  disabled,
}: {
  label: string;
  icon: ReturnType<typeof feather>;
  onPress: () => void;
  disabled?: boolean;
}) {
  return (
    <Pressable
      onPress={onPress}
      disabled={disabled}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [styles.tile, pressed && styles.pressed, disabled && styles.disabled]}
    >
      <AppIcon icon={icon} size={22} color={SV_TEAL} />
      <Text style={styles.tileLabel}>{label}</Text>
    </Pressable>
  );
}

type ListProps = {
  attachments: ServiceAttachment[];
  onRemove: (id: string) => void;
  onReplace: (att: ServiceAttachment) => void;
  onEditCaption: (att: ServiceAttachment) => void;
  tr: (key: StringKey) => string;
};

export function ServiceMediaRows({ attachments, onRemove, onReplace, onEditCaption, tr }: ListProps) {
  if (!attachments.length) return null;
  return (
    <View style={styles.rows}>
      {attachments.map((att) => (
        <View key={att.id} style={styles.row}>
          <View style={styles.rowIcon}>
            <AppIcon icon={rowIcon(att.kind)} size={16} color={SV_TEAL} />
          </View>
          <Pressable
            onPress={() => onEditCaption(att)}
            style={styles.rowCopy}
            accessibilityRole="button"
            accessibilityLabel={tr('servicesEditCaption')}
          >
            <Text style={styles.rowTitle} numberOfLines={1}>
              {att.filename || att.url || att.id}
            </Text>
            <Text style={styles.rowMeta} numberOfLines={1}>
              {att.caption || att.kind}
            </Text>
          </Pressable>
          <Pressable
            onPress={() =>
              Alert.alert(att.filename || att.url || tr('servicesMediaSection'), undefined, [
                { text: tr('servicesReplace'), onPress: () => onReplace(att) },
                {
                  text: tr('servicesRemove'),
                  style: 'destructive',
                  onPress: () => onRemove(att.id),
                },
                { text: tr('usersCancel'), style: 'cancel' },
              ])
            }
            accessibilityRole="button"
            accessibilityLabel={tr('servicesResourceMenu')}
            style={styles.more}
          >
            <AppIcon icon={feather('more-horizontal')} size={20} color={SV_MUTED} />
          </Pressable>
        </View>
      ))}
    </View>
  );
}

function rowIcon(kind: ServiceKind): ReturnType<typeof feather> {
  if (kind === 'image') return feather('image');
  if (kind === 'video') return feather('play-circle');
  if (kind === 'link') return feather('link');
  return feather('file');
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', gap: 8 },
  tile: {
    flex: 1,
    minHeight: 76,
    borderWidth: 1,
    borderColor: SV_BORDER,
    borderRadius: SV_RADIUS,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: '#FFFFFF',
    paddingVertical: 12,
  },
  tileLabel: {
    color: SV_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    fontWeight: '600',
  },
  pressed: { opacity: 0.7 },
  disabled: { opacity: 0.45 },
  countRow: { flexDirection: 'row', alignItems: 'center', gap: 6, marginTop: 10 },
  count: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 13 },
  rows: { gap: 8, marginTop: 8 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: SV_BORDER,
    borderRadius: SV_RADIUS,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  rowIcon: {
    width: 32,
    height: 32,
    borderRadius: SV_RADIUS_SM,
    backgroundColor: SV_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowCopy: { flex: 1, gap: 2 },
  rowTitle: {
    color: SV_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '600',
  },
  rowMeta: { color: SV_MUTED, fontFamily: fonts.body, fontSize: 12 },
  more: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
});

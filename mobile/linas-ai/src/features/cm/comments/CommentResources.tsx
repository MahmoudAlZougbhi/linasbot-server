import { Alert, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { CM_BORDER, CM_MUTED, CM_RADIUS, CM_RADIUS_SM, CM_TEAL, CM_TEAL_DARK, CM_TEAL_SOFT } from './commentChrome';
import {
  allowedResourceKinds,
  formatDuration,
  type CommentAttachment,
  type CommentKind,
  type CommentReplyIn,
} from './commentModel';

type GridProps = {
  replyIn: CommentReplyIn;
  disabled?: boolean;
  onAdd: (kind: CommentKind) => void;
  tr: (key: StringKey) => string;
};

const KIND_META: Record<CommentKind, { label: StringKey; icon: ReturnType<typeof feather> }> = {
  image: { label: 'commentsAddImage', icon: feather('image') },
  video: { label: 'commentsAddVideo', icon: feather('play-circle') },
  file: { label: 'commentsAddFile', icon: feather('file') },
  link: { label: 'commentsAddLink', icon: feather('link') },
};

export function CommentResourceGrid({ replyIn, disabled, onAdd, tr }: GridProps) {
  const kinds = allowedResourceKinds(replyIn);
  return (
    <View style={styles.grid}>
      {kinds.map((kind) => (
        <Pressable
          key={kind}
          onPress={() => onAdd(kind)}
          disabled={disabled}
          accessibilityRole="button"
          accessibilityLabel={tr(KIND_META[kind].label)}
          style={({ pressed }) => [
            styles.tile,
            kinds.length === 2 && styles.tileWide,
            pressed && styles.pressed,
            disabled && styles.disabled,
          ]}
        >
          <AppIcon icon={KIND_META[kind].icon} size={22} color={CM_TEAL} />
          <Text style={styles.tileLabel}>{tr(KIND_META[kind].label)}</Text>
        </Pressable>
      ))}
    </View>
  );
}

type ListProps = {
  attachments: CommentAttachment[];
  onRemove: (id: string) => void;
  onReplace: (att: CommentAttachment) => void;
  onEditCaption: (att: CommentAttachment) => void;
  tr: (key: StringKey) => string;
};

export function CommentResourceRows({ attachments, onRemove, onReplace, onEditCaption, tr }: ListProps) {
  if (!attachments.length) return null;
  return (
    <View style={styles.rows}>
      {attachments.map((att) => (
        <View key={att.id} style={styles.row}>
          <View style={styles.rowIcon}>
            <AppIcon icon={KIND_META[att.kind].icon} size={16} color={CM_TEAL} />
          </View>
          <Pressable
            onPress={() => {
              if (att.kind === 'link' && att.url) {
                void Linking.openURL(att.url);
                return;
              }
              onEditCaption(att);
            }}
            style={styles.rowCopy}
            accessibilityRole="button"
            accessibilityLabel={tr('commentsTapToOpen')}
          >
            <Text style={styles.rowTitle} numberOfLines={1}>
              {att.filename || att.url || att.id}
            </Text>
            <Text style={styles.rowMeta} numberOfLines={1}>
              {rowMeta(att, tr)}
            </Text>
          </Pressable>
          <Pressable
            onPress={() =>
              Alert.alert(att.filename || att.url || tr('commentsResources'), undefined, [
                att.kind === 'link' && att.url
                  ? { text: tr('commentsOpen'), onPress: () => void Linking.openURL(att.url) }
                  : { text: tr('commentsEditCaption'), onPress: () => onEditCaption(att) },
                { text: tr('commentsReplace'), onPress: () => onReplace(att) },
                { text: tr('commentsRemove'), style: 'destructive', onPress: () => onRemove(att.id) },
                { text: tr('usersCancel'), style: 'cancel' },
              ])
            }
            accessibilityRole="button"
            accessibilityLabel={tr('commentsResourceMenu')}
            style={styles.more}
          >
            <AppIcon icon={feather('more-horizontal')} size={20} color={CM_MUTED} />
          </Pressable>
        </View>
      ))}
    </View>
  );
}

function rowMeta(att: CommentAttachment, tr: (key: StringKey) => string): string {
  const kindLabel =
    att.kind === 'image'
      ? tr('commentsKindImage')
      : att.kind === 'video'
        ? tr('commentsKindVideo')
        : att.kind === 'link'
          ? tr('commentsKindLink')
          : tr('commentsKindFile');
  if (att.kind === 'video' && att.duration_seconds != null && att.duration_seconds > 0) {
    return `${kindLabel} · ${formatDuration(att.duration_seconds)} · ${tr('commentsTapToOpen')}`;
  }
  return `${kindLabel} · ${tr('commentsTapToOpen')}`;
}

const styles = StyleSheet.create({
  grid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  tile: {
    width: '47%',
    flexGrow: 1,
    minHeight: 76,
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 6,
    backgroundColor: '#FFFFFF',
    paddingVertical: 12,
  },
  tileWide: { width: '48%' },
  tileLabel: {
    color: CM_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 13,
    fontWeight: '600',
  },
  pressed: { opacity: 0.7 },
  disabled: { opacity: 0.45 },
  rows: { gap: 8, marginTop: 8 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  rowIcon: {
    width: 32,
    height: 32,
    borderRadius: CM_RADIUS_SM,
    backgroundColor: CM_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  rowCopy: { flex: 1, gap: 2 },
  rowTitle: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '700',
  },
  rowMeta: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 12 },
  more: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
});

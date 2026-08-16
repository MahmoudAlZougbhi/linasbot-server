import { Alert, Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import {
  KN_BORDER,
  KN_MUTED,
  KN_PDF,
  KN_RADIUS,
  KN_RADIUS_SM,
  KN_TEAL,
  KN_TEAL_DARK,
  KN_TEAL_SOFT,
} from './knowledgeChrome';
import {
  formatBytes,
  formatDuration,
  isPdfAttachment,
  normalizeAttachmentKind,
  type KnowledgeAttachment,
  type KnowledgeKind,
} from './knowledgeModel';

type GridProps = {
  onAdd: (kind: KnowledgeKind) => void;
  tr: (key: StringKey) => string;
};

export function KnowledgeResourceGrid({ onAdd, tr }: GridProps) {
  return (
    <View style={styles.grid}>
      <ResourceTile
        label={tr('knowledgeAddImage')}
        icon={feather('image')}
        onPress={() => onAdd('image')}
      />
      <ResourceTile
        label={tr('knowledgeAddVideo')}
        icon={feather('play-circle')}
        onPress={() => onAdd('video')}
      />
      <ResourceTile
        label={tr('knowledgeAddFile')}
        icon={feather('file')}
        onPress={() => onAdd('file')}
      />
      <ResourceTile
        label={tr('knowledgeAddLink')}
        icon={feather('link')}
        onPress={() => onAdd('link')}
      />
    </View>
  );
}

function ResourceTile({
  label,
  icon,
  onPress,
}: {
  label: string;
  icon: ReturnType<typeof feather>;
  onPress: () => void;
}) {
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={label}
      style={({ pressed }) => [styles.tile, pressed && styles.pressed]}
    >
      <AppIcon icon={icon} size={26} color={KN_TEAL} />
      <Text style={styles.tileLabel}>{label}</Text>
    </Pressable>
  );
}

type ListProps = {
  attachments: KnowledgeAttachment[];
  onRemove: (id: string) => void;
  onReplace: (att: KnowledgeAttachment) => void;
  onEditCaption: (att: KnowledgeAttachment) => void;
  onMove?: (id: string, direction: -1 | 1) => void;
  tr: (key: StringKey) => string;
};

export function KnowledgeResourceRows({
  attachments,
  onRemove,
  onReplace,
  onEditCaption,
  onMove,
  tr,
}: ListProps) {
  return (
    <View style={styles.rows}>
      {attachments.map((raw) => {
        const att = normalizeAttachmentKind(raw);
        const heading = att.title || att.filename || att.url || att.id;
        const detail = att.description || att.caption || rowMeta(att, tr);
        return (
          <View key={att.id} style={styles.row}>
            <View style={[styles.rowIcon, att.kind === 'file' && isPdfAttachment(att) && styles.pdfIcon]}>
              <AppIcon
                icon={rowIcon(att)}
                size={18}
                color={att.kind === 'file' && isPdfAttachment(att) ? KN_PDF : KN_TEAL}
              />
            </View>
            <Pressable
              onPress={() => onEditCaption(att)}
              style={styles.rowCopy}
              accessibilityRole="button"
              accessibilityLabel={tr('resourceEdit')}
            >
              <Text style={styles.rowTitle} numberOfLines={1}>
                {heading}
              </Text>
              <Text style={styles.rowMeta} numberOfLines={2}>
                {rowMeta(att, tr)}
                {detail && detail !== rowMeta(att, tr) ? ` · ${detail}` : ''}
              </Text>
            </Pressable>
            <Pressable
              onPress={() =>
                Alert.alert(heading, undefined, [
                  { text: tr('resourceEdit'), onPress: () => onEditCaption(att) },
                  { text: tr('knowledgeReplace'), onPress: () => onReplace(att) },
                  ...(onMove
                    ? [
                        { text: tr('resourceMoveUp'), onPress: () => onMove(att.id, -1) },
                        { text: tr('resourceMoveDown'), onPress: () => onMove(att.id, 1) },
                      ]
                    : []),
                  {
                    text: tr('knowledgeRemove'),
                    style: 'destructive' as const,
                    onPress: () => onRemove(att.id),
                  },
                  { text: tr('usersCancel'), style: 'cancel' as const },
                ])
              }
              accessibilityRole="button"
              accessibilityLabel={tr('knowledgeResourceMenu')}
              style={styles.more}
            >
              <AppIcon icon={feather('more-horizontal')} size={20} color={KN_MUTED} />
            </Pressable>
          </View>
        );
      })}
    </View>
  );
}

function rowIcon(att: KnowledgeAttachment): ReturnType<typeof feather> {
  if (att.kind === 'image') return feather('image');
  if (att.kind === 'video') return feather('play-circle');
  if (att.kind === 'link') return feather('link');
  if (isPdfAttachment(att)) return feather('file-text');
  return feather('file');
}

function rowMeta(att: KnowledgeAttachment, tr: (key: StringKey) => string): string {
  if (att.kind === 'image') return tr('knowledgeKindImage');
  if (att.kind === 'video') {
    const dur =
      att.duration_seconds != null && att.duration_seconds > 0
        ? formatDuration(att.duration_seconds)
        : '';
    return dur ? `${tr('knowledgeKindVideo')} • ${dur}` : tr('knowledgeKindVideo');
  }
  if (att.kind === 'link') return att.url || tr('knowledgeKindLink');
  if (isPdfAttachment(att)) {
    return att.size > 0
      ? `${tr('knowledgeKindPdf')} • ${formatBytes(att.size)}`
      : tr('knowledgeKindPdf');
  }
  return att.size > 0
    ? `${tr('knowledgeKindFile')} • ${formatBytes(att.size)}`
    : tr('knowledgeKindFile');
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: 10,
  },
  tile: {
    width: '47%',
    flexGrow: 1,
    minHeight: 88,
    borderWidth: 1,
    borderColor: KN_BORDER,
    borderRadius: KN_RADIUS,
    alignItems: 'center',
    justifyContent: 'center',
    gap: 8,
    backgroundColor: '#FFFFFF',
    paddingVertical: 16,
  },
  tileLabel: {
    color: KN_TEAL,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '600',
  },
  pressed: { opacity: 0.7 },
  rows: { gap: 8, marginTop: 4 },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: KN_BORDER,
    borderRadius: KN_RADIUS,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  rowIcon: {
    width: 36,
    height: 36,
    borderRadius: KN_RADIUS_SM,
    backgroundColor: KN_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  pdfIcon: { backgroundColor: '#FCE7F0' },
  rowCopy: { flex: 1, gap: 2 },
  rowTitle: {
    color: KN_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    fontWeight: '600',
  },
  rowMeta: { color: KN_MUTED, fontFamily: fonts.body, fontSize: 12 },
  more: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
});

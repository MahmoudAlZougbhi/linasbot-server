import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';

import { SideDrawer } from '../../components/SideDrawer';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';

type Item = { id: string; title: string };

type Props = {
  open: boolean;
  onClose: () => void;
  history: Item[];
  pinnedIds: string[];
  activeId: string | null;
  onNewChat: () => void;
  onOpen: (id: string) => void;
  onTogglePin: (id: string) => void;
};

export function HistoryDrawer({
  open,
  onClose,
  history,
  pinnedIds,
  activeId,
  onNewChat,
  onOpen,
  onTogglePin,
}: Props) {
  const { tr, isRtl } = useI18n();
  const pinned = history.filter((h) => pinnedIds.includes(h.id));
  const rest = history.filter((h) => !pinnedIds.includes(h.id));

  return (
    <SideDrawer open={open} side={isRtl ? 'right' : 'left'} onClose={onClose}>
      <Text style={styles.heading}>{tr('history')}</Text>
      <Pressable style={styles.newBtn} onPress={onNewChat}>
        <Text style={styles.newText}>+ {tr('newChat')}</Text>
      </Pressable>
      <ScrollView contentContainerStyle={styles.list}>
        {pinned.length > 0 ? <Text style={styles.section}>{tr('pinnedChats')}</Text> : null}
        {pinned.map((item) => (
          <HistoryRow
            key={item.id}
            item={item}
            active={item.id === activeId}
            pinned
            untitledLabel={tr('untitledChat')}
            onOpen={onOpen}
            onTogglePin={onTogglePin}
          />
        ))}
        <Text style={styles.section}>{tr('recentChats')}</Text>
        {rest.map((item) => (
          <HistoryRow
            key={item.id}
            item={item}
            active={item.id === activeId}
            pinned={false}
            untitledLabel={tr('untitledChat')}
            onOpen={onOpen}
            onTogglePin={onTogglePin}
          />
        ))}
        {history.length === 0 ? (
          <Text style={styles.empty}>{tr('noConversationsYet')}</Text>
        ) : null}
      </ScrollView>
    </SideDrawer>
  );
}

function HistoryRow({
  item,
  active,
  pinned,
  untitledLabel,
  onOpen,
  onTogglePin,
}: {
  item: Item;
  active: boolean;
  pinned: boolean;
  untitledLabel: string;
  onOpen: (id: string) => void;
  onTogglePin: (id: string) => void;
}) {
  return (
    <View style={[styles.row, active && styles.rowActive]}>
      <Pressable style={styles.rowMain} onPress={() => onOpen(item.id)}>
        <Text style={styles.rowTitle} numberOfLines={2}>
          {item.title || untitledLabel}
        </Text>
      </Pressable>
      <Pressable onPress={() => onTogglePin(item.id)} hitSlop={8}>
        <Text style={styles.pin}>{pinned ? '★' : '☆'}</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  heading: {
    color: colors.text,
    fontFamily: fonts.display,
    fontSize: 22,
    marginBottom: spacing.md,
  },
  newBtn: {
    backgroundColor: colors.accentSoft,
    borderRadius: radii.md,
    paddingVertical: spacing.md,
    alignItems: 'center',
    marginBottom: spacing.lg,
    borderWidth: 1,
    borderColor: colors.accent,
  },
  newText: { color: colors.accent, fontFamily: fonts.bodyMedium, fontWeight: '700' },
  list: { paddingBottom: 40, gap: 4 },
  section: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    marginTop: spacing.md,
    marginBottom: spacing.sm,
    textTransform: 'uppercase',
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radii.sm,
    paddingVertical: 10,
    paddingHorizontal: 10,
    marginBottom: 2,
  },
  rowActive: { backgroundColor: colors.surfaceAlt },
  rowMain: { flex: 1, paddingRight: 8 },
  rowTitle: {
    color: colors.text,
    fontFamily: fonts.bodyMedium,
    fontWeight: '500',
    fontSize: 15,
  },
  pin: { color: colors.warning, fontSize: 18, paddingHorizontal: 4 },
  empty: { color: colors.textMuted, marginTop: spacing.lg },
});

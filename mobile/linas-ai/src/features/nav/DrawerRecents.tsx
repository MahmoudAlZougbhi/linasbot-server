import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { HistoryRows, type HistoryItem } from './HistoryRows';
import { NEW_CHAT_ICON } from './moduleIcons';

type Props = {
  items: HistoryItem[];
  pinnedIds: string[];
  activeId: string | null;
  archivedMode: boolean;
  emptyLabel: string;
  onNewChat: () => void;
  onOpen: (id: string) => void;
  onTogglePin: (id: string) => void;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
};

export function DrawerRecents(props: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const pinned = props.items.filter((h) => props.pinnedIds.includes(h.id));
  const recent = props.items.filter((h) => !props.pinnedIds.includes(h.id));

  const rowProps = {
    pinnedIds: props.pinnedIds,
    activeId: props.activeId,
    archivedMode: props.archivedMode,
    emptyLabel: props.emptyLabel,
    variant: 'drawer' as const,
    onOpen: props.onOpen,
    onTogglePin: props.onTogglePin,
    onArchive: props.onArchive,
    onUnarchive: props.onUnarchive,
    onRename: props.onRename,
    onDelete: props.onDelete,
  };

  return (
    <View style={styles.wrap}>
      <View style={[styles.separator, { backgroundColor: colors.border }]} />
      {pinned.length ? (
        <View style={styles.sectionBlock}>
          <Text style={[styles.heading, { color: colors.text }]} accessibilityRole="header">
            {tr('drawerPin')}
          </Text>
          <HistoryRows {...rowProps} items={pinned} emptyLabel="" />
        </View>
      ) : null}
      <View style={styles.sectionBlock}>
        <View style={styles.headingRow}>
          <Text style={[styles.heading, { color: colors.text }]} accessibilityRole="header">
            {tr('drawerRecents')}
          </Text>
          <Pressable
            onPress={props.onNewChat}
            accessibilityRole="button"
            accessibilityLabel={tr('newChat')}
            hitSlop={10}
            style={styles.newChatHit}
          >
            <AppIcon icon={NEW_CHAT_ICON} size={20} color={colors.text} />
          </Pressable>
        </View>
        <HistoryRows {...rowProps} items={recent} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.md },
  separator: { height: StyleSheet.hairlineWidth, marginBottom: spacing.sm },
  sectionBlock: { gap: spacing.sm },
  headingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
  },
  heading: {
    fontFamily: fonts.display,
    fontSize: 18,
    letterSpacing: -0.25,
  },
  newChatHit: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
});

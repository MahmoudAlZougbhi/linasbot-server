import { Pressable, ScrollView, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

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
  const insets = useSafeAreaInsets();

  return (
    <View style={styles.wrap}>
      <View style={[styles.separator, { backgroundColor: colors.border }]} />
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
      <ScrollView
        style={styles.list}
        contentContainerStyle={[
          styles.listContent,
          { paddingBottom: Math.max(insets.bottom, 8) },
        ]}
        keyboardShouldPersistTaps="handled"
        keyboardDismissMode="on-drag"
        showsVerticalScrollIndicator={false}
        removeClippedSubviews={false}
      >
        <HistoryRows
          items={props.items}
          pinnedIds={props.pinnedIds}
          activeId={props.activeId}
          archivedMode={props.archivedMode}
          emptyLabel={props.emptyLabel}
          variant="drawer"
          onOpen={props.onOpen}
          onTogglePin={props.onTogglePin}
          onArchive={props.onArchive}
          onUnarchive={props.onUnarchive}
          onRename={props.onRename}
          onDelete={props.onDelete}
        />
      </ScrollView>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flex: 1, minHeight: 0, gap: spacing.md },
  separator: { height: StyleSheet.hairlineWidth, marginBottom: spacing.sm, flexShrink: 0 },
  headingRow: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: spacing.sm,
    flexShrink: 0,
  },
  heading: {
    fontFamily: fonts.display,
    fontSize: 18,
    letterSpacing: -0.25,
  },
  newChatHit: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  list: { flex: 1, minHeight: 0 },
  listContent: { flexGrow: 1 },
});

import { StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../theme';
import { HistoryRows, type HistoryItem } from './HistoryRows';

type Props = {
  items: HistoryItem[];
  pinnedIds: string[];
  activeId: string | null;
  archivedMode: boolean;
  emptyLabel: string;
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

  return (
    <View style={styles.wrap}>
      <View style={[styles.separator, { backgroundColor: colors.border }]} />
      <Text style={[styles.heading, { color: colors.text }]} accessibilityRole="header">
        {tr('drawerRecents')}
      </Text>
      <HistoryRows {...props} variant="drawer" />
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { flexGrow: 1, gap: spacing.sm },
  separator: { height: StyleSheet.hairlineWidth, marginBottom: spacing.sm },
  heading: {
    fontFamily: fonts.bodyMedium,
    fontWeight: '700',
    fontSize: 15,
    marginBottom: spacing.xs,
  },
});

import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon } from '../../components/AppIcon';
import { fonts, radii, spacing, useTheme } from '../../theme';
import { DRAWER_TOOL_ICONS } from './moduleIcons';

export type HistoryItem = { id: string; title: string };

type Props = {
  items: HistoryItem[];
  pinnedIds: string[];
  activeId: string | null;
  archivedMode: boolean;
  emptyLabel: string;
  variant?: 'default' | 'drawer';
  onOpen: (id: string) => void;
  onTogglePin: (id: string) => void;
  onArchive: (id: string) => void;
  onUnarchive: (id: string) => void;
  onRename: (id: string, title: string) => void;
  onDelete: (id: string) => void;
};

export function HistoryRows({
  items,
  pinnedIds,
  activeId,
  archivedMode,
  emptyLabel,
  variant = 'default',
  onOpen,
  onTogglePin,
  onArchive,
  onUnarchive,
  onRename,
  onDelete,
}: Props) {
  const { colors } = useTheme();
  const [menuId, setMenuId] = useState<string | null>(null);
  const [renameId, setRenameId] = useState<string | null>(null);
  const [renameText, setRenameText] = useState('');
  const drawer = variant === 'drawer';

  const pinned = items.filter((h) => pinnedIds.includes(h.id));
  const rest = items.filter((h) => !pinnedIds.includes(h.id));
  const drawerRows = drawer ? [...pinned, ...rest] : rest;

  const renderRow = (item: HistoryItem) => {
    const active = item.id === activeId;
    return (
      <View key={item.id}>
        <View
          style={[
            styles.row,
            drawer && styles.rowDrawer,
            active && { backgroundColor: drawer ? colors.activeRow : colors.activeRow },
          ]}
        >
          {!drawer && active ? (
            <View style={[styles.indicator, { backgroundColor: colors.activeIndicator }]} />
          ) : !drawer ? (
            <View style={styles.indicatorSpacer} />
          ) : null}
          <Pressable
            style={[styles.main, drawer && styles.mainDrawer]}
            onPress={() => onOpen(item.id)}
            onLongPress={() => setMenuId((m) => (m === item.id ? null : item.id))}
            delayLongPress={350}
            accessibilityRole="button"
            accessibilityLabel={item.title || 'Untitled conversation'}
            accessibilityHint="Long press to rename, pin, archive, or delete"
          >
            {!drawer && pinnedIds.includes(item.id) && !archivedMode ? (
              <AppIcon icon={DRAWER_TOOL_ICONS.pin} size={14} color={colors.textDim} />
            ) : null}
            {renameId === item.id ? (
              <TextInput
                value={renameText}
                onChangeText={setRenameText}
                onSubmitEditing={() => {
                  onRename(item.id, renameText);
                  setRenameId(null);
                }}
                onBlur={() => {
                  onRename(item.id, renameText);
                  setRenameId(null);
                }}
                autoFocus
                style={{ color: colors.text, flex: 1 }}
              />
            ) : (
              <Text
                style={[
                  styles.rowTitle,
                  drawer && styles.rowTitleDrawer,
                  { color: colors.text },
                ]}
                numberOfLines={drawer ? 1 : 2}
              >
                {item.title || 'Untitled'}
              </Text>
            )}
          </Pressable>
          {drawer && active ? (
            <Pressable
              onPress={() => setMenuId((m) => (m === item.id ? null : item.id))}
              accessibilityRole="button"
              accessibilityLabel="Conversation actions"
              hitSlop={8}
              style={styles.overflowDrawer}
            >
              <AppIcon icon={DRAWER_TOOL_ICONS.overflow} size={18} color={colors.textMuted} />
            </Pressable>
          ) : !drawer ? (
            <Pressable
              onPress={() => setMenuId((m) => (m === item.id ? null : item.id))}
              accessibilityRole="button"
              accessibilityLabel="Conversation actions"
              hitSlop={8}
              style={styles.overflow}
            >
              <AppIcon icon={DRAWER_TOOL_ICONS.overflow} size={18} color={colors.textMuted} />
            </Pressable>
          ) : null}
        </View>
        {menuId === item.id ? (
          <View style={[styles.menu, { backgroundColor: colors.surface, borderColor: colors.border }]}>
            {!archivedMode ? (
              <MenuAction
                label={pinnedIds.includes(item.id) ? 'Unpin' : 'Pin'}
                onPress={() => {
                  onTogglePin(item.id);
                  setMenuId(null);
                }}
              />
            ) : null}
            <MenuAction
              label="Rename"
              onPress={() => {
                setRenameId(item.id);
                setRenameText(item.title || '');
                setMenuId(null);
              }}
            />
            <MenuAction
              label={archivedMode ? 'Unarchive' : 'Archive'}
              onPress={() => {
                if (archivedMode) onUnarchive(item.id);
                else onArchive(item.id);
                setMenuId(null);
              }}
            />
            <MenuAction
              label="Delete"
              danger
              onPress={() => {
                setMenuId(null);
                onDelete(item.id);
              }}
            />
          </View>
        ) : null}
      </View>
    );
  };

  const renderSection = (label: string, rows: HistoryItem[]) => {
    if (!rows.length) return null;
    return (
      <View key={label}>
        {!drawer ? (
          <Text style={[styles.section, { color: colors.textDim }]}>{label}</Text>
        ) : null}
        {rows.map(renderRow)}
      </View>
    );
  };

  if (!items.length) {
    return (
      <Text
        style={{ color: colors.textMuted, marginTop: drawer ? 0 : spacing.md }}
        accessibilityRole="text"
        accessibilityLabel={emptyLabel}
      >
        {emptyLabel}
      </Text>
    );
  }

  if (drawer) {
    return <View>{drawerRows.map(renderRow)}</View>;
  }

  return (
    <View>
      {!archivedMode ? renderSection('Pinned', pinned) : null}
      {renderSection(archivedMode ? 'Archived' : 'Recent', archivedMode ? items : rest)}
    </View>
  );
}

function MenuAction({
  label,
  onPress,
  danger,
}: {
  label: string;
  onPress: () => void;
  danger?: boolean;
}) {
  const { colors } = useTheme();
  return (
    <Pressable onPress={onPress} style={styles.menuItem} accessibilityLabel={label}>
      <Text style={{ color: danger ? colors.danger : colors.text }}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  section: {
    fontFamily: fonts.bodyMedium,
    fontSize: 10,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    marginTop: spacing.md,
    marginBottom: spacing.sm,
  },
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    borderRadius: radii.sm,
    minHeight: 48,
    marginBottom: 2,
  },
  rowDrawer: {
    minHeight: 42,
    borderRadius: radii.md,
    marginBottom: 4,
    paddingHorizontal: 4,
  },
  indicator: { width: 3, alignSelf: 'stretch', borderRadius: 2, marginRight: 8 },
  indicatorSpacer: { width: 3, marginRight: 8 },
  main: {
    flex: 1,
    paddingVertical: 10,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
    minHeight: 44,
  },
  mainDrawer: {
    paddingVertical: 8,
    paddingHorizontal: 8,
    minHeight: 38,
  },
  rowTitle: {
    fontFamily: fonts.bodyMedium,
    fontWeight: '500',
    flex: 1,
    fontSize: 14,
    lineHeight: 20,
  },
  rowTitleDrawer: {
    fontFamily: fonts.bodyMedium,
    fontWeight: '600',
    fontSize: 15,
    lineHeight: 20,
    letterSpacing: -0.15,
  },
  overflow: { width: 44, height: 44, alignItems: 'center', justifyContent: 'center' },
  overflowDrawer: { width: 36, height: 36, alignItems: 'center', justifyContent: 'center' },
  menu: {
    marginLeft: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderRadius: radii.md,
    overflow: 'hidden',
  },
  menuItem: { minHeight: 44, paddingHorizontal: 12, justifyContent: 'center' },
});

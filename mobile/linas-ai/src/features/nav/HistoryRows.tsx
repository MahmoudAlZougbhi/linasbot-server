import { useState } from 'react';
import { Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { fonts, radii, spacing, useTheme } from '../../theme';

export type HistoryItem = { id: string; title: string };

type Props = {
  items: HistoryItem[];
  pinnedIds: string[];
  activeId: string | null;
  archivedMode: boolean;
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

  const pinned = items.filter((h) => pinnedIds.includes(h.id));
  const rest = items.filter((h) => !pinnedIds.includes(h.id));

  const renderSection = (label: string, rows: HistoryItem[]) => {
    if (!rows.length) return null;
    return (
      <View key={label}>
        <Text style={[styles.section, { color: colors.textDim }]}>{label}</Text>
        {rows.map((item) => {
          const active = item.id === activeId;
          return (
            <View key={item.id}>
              <View
                style={[
                  styles.row,
                  active && { backgroundColor: colors.activeRow },
                ]}
              >
                {active ? (
                  <View style={[styles.indicator, { backgroundColor: colors.activeIndicator }]} />
                ) : (
                  <View style={styles.indicatorSpacer} />
                )}
                <Pressable style={styles.main} onPress={() => onOpen(item.id)}>
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
                    <Text style={{ color: colors.text, fontFamily: fonts.body }} numberOfLines={2}>
                      {item.title || 'Untitled'}
                    </Text>
                  )}
                </Pressable>
                <Pressable
                  onPress={() => setMenuId((m) => (m === item.id ? null : item.id))}
                  accessibilityLabel="Conversation actions"
                  hitSlop={8}
                  style={styles.overflow}
                >
                  <Text style={{ color: colors.textMuted }}>⋯</Text>
                </Pressable>
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
        })}
      </View>
    );
  };

  if (!items.length) {
    return (
      <Text style={{ color: colors.textMuted, marginTop: spacing.md }}>
        {archivedMode ? 'No archived chats.' : 'No conversations yet.'}
      </Text>
    );
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
    fontSize: 11,
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
  indicator: { width: 3, alignSelf: 'stretch', borderRadius: 2, marginRight: 8 },
  indicatorSpacer: { width: 3, marginRight: 8 },
  main: { flex: 1, paddingVertical: 10 },
  overflow: { width: 40, height: 40, alignItems: 'center', justifyContent: 'center' },
  menu: {
    marginLeft: 12,
    marginBottom: 8,
    borderWidth: 1,
    borderRadius: radii.md,
    overflow: 'hidden',
  },
  menuItem: { minHeight: 44, paddingHorizontal: 12, justifyContent: 'center' },
});

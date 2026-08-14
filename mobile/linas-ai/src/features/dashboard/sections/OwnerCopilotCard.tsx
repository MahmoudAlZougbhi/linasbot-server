import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { StringKey } from '../../../i18n';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, spacing, useTheme } from '../../../theme';
import { DASH_CARD_RADIUS, DASH_FOREST } from '../dashboardChrome';
import { formatCount } from '../dashboardFormat';
import type { TenantDashboard } from '../dashboardTypes';

type Copilot = TenantDashboard['activity_summary']['owner_copilot'];
type CopilotUser = NonNullable<NonNullable<Copilot>['by_user']>[number];

type Props = {
  copilot: Copilot | undefined;
  expanded: boolean;
  onToggle: () => void;
  onOpenChat: () => void;
};

export function OwnerCopilotCard({ copilot, expanded, onToggle, onOpenChat }: Props) {
  const { colors } = useTheme();
  const { tr } = useI18n();
  const credits = copilot?.credits ?? 0;
  const chats = copilot?.chats ?? 0;
  const users = copilot?.users ?? 0;
  const meta = tr('dashOwnerCopilotMeta')
    .replace('{credits}', formatCount(credits))
    .replace('{chats}', formatCount(chats))
    .replace('{users}', formatCount(users));
  const rows = copilot?.by_user ?? [];

  return (
    <Pressable
      onPress={onToggle}
      accessibilityRole="button"
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
    >
      <View style={styles.top}>
        <Ionicons name="sparkles" size={20} color={DASH_FOREST} />
        <View style={styles.body}>
          <Text style={[styles.title, { color: colors.text }]}>{tr('dashOwnerCopilot')}</Text>
          <Text style={[styles.meta, { color: colors.textMuted }]}>{meta}</Text>
        </View>
        <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={18} color={colors.textDim} />
      </View>
      {expanded ? (
        <View style={styles.expand}>
          {rows.map((row, index) => (
            <UserRow key={row.user_id ?? `unattributed-${index}`} row={row} colors={colors} tr={tr} />
          ))}
          <Pressable onPress={onOpenChat} style={styles.openChat} accessibilityRole="button">
            <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>{tr('dashOpenOwnerChat')}</Text>
          </Pressable>
        </View>
      ) : null}
    </Pressable>
  );
}

function UserRow({
  row,
  colors,
  tr,
}: {
  row: CopilotUser;
  colors: { text: string; textMuted: string; borderSoft: string };
  tr: (key: StringKey) => string;
}) {
  const name = row.unattributed || !row.name ? tr('dashUnattributed') : row.name;
  const line = tr('dashCopilotUserMeta')
    .replace('{chats}', formatCount(row.chats))
    .replace('{credits}', formatCount(row.credits));
  return (
    <View style={[styles.userRow, { borderTopColor: colors.borderSoft }]}>
      <Text style={[styles.userName, { color: colors.text }]} numberOfLines={1}>
        {name}
      </Text>
      <Text style={[styles.userMeta, { color: colors.textMuted }]}>{line}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: DASH_CARD_RADIUS,
    borderWidth: 1,
    padding: spacing.md,
    gap: spacing.sm,
  },
  top: { flexDirection: 'row', alignItems: 'center', gap: spacing.md },
  body: { flex: 1, gap: 2 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  meta: { fontFamily: fonts.body, fontSize: 12 },
  expand: { gap: 0, paddingLeft: 36 },
  userRow: {
    borderTopWidth: StyleSheet.hairlineWidth,
    paddingVertical: 8,
    flexDirection: 'row',
    justifyContent: 'space-between',
    gap: spacing.sm,
  },
  userName: { fontFamily: fonts.bodyMedium, fontSize: 13, flex: 1 },
  userMeta: { fontFamily: fonts.body, fontSize: 12 },
  openChat: { marginTop: 8 },
});

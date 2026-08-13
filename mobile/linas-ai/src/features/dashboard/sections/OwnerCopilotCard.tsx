import { Ionicons } from '@expo/vector-icons';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import { useI18n } from '../../../i18n/LanguageContext';
import { fonts, radii, spacing, useTheme } from '../../../theme';
import { formatCount } from '../dashboardFormat';
import type { TenantDashboard } from '../dashboardTypes';

type Copilot = TenantDashboard['activity_summary']['owner_copilot'];

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

  return (
    <Pressable
      onPress={onToggle}
      accessibilityRole="button"
      style={[styles.card, { backgroundColor: colors.surface, borderColor: colors.border }]}
    >
      <View style={[styles.iconWrap, { backgroundColor: colors.accentSoft }]}>
        <Ionicons name="sparkles" size={20} color={colors.accent} />
      </View>
      <View style={styles.body}>
        <Text style={[styles.title, { color: colors.text }]}>{tr('dashOwnerCopilot')}</Text>
        <Text style={[styles.meta, { color: colors.textMuted }]}>{meta}</Text>
        {expanded ? (
          <Pressable onPress={onOpenChat} style={{ marginTop: 8 }} accessibilityRole="button">
            <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>{tr('dashOpenOwnerChat')}</Text>
          </Pressable>
        ) : null}
      </View>
      <Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={18} color={colors.textDim} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    borderRadius: radii.lg,
    borderWidth: 1,
    padding: spacing.md,
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.md,
  },
  iconWrap: {
    width: 40,
    height: 40,
    borderRadius: 20,
    alignItems: 'center',
    justifyContent: 'center',
  },
  body: { flex: 1, gap: 2 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  meta: { fontFamily: fonts.body, fontSize: 12 },
});

import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { KN_BORDER, KN_ICON_SQ, KN_MUTED, KN_RADIUS, KN_TEAL, KN_TEAL_DARK, KN_TEAL_SOFT } from './knowledgeChrome';
import {
  countMedia,
  formatMediaSummary,
  formatUpdatedStamp,
  LOCATIONS_KNOWLEDGE_TITLE,
  type KnowledgeItem,
} from './knowledgeModel';

type Props = {
  title: string;
  summary: string;
  updated: string;
  onPress: () => void;
};

export function KnowledgeCard({ title, summary, updated, onPress }: Props) {
  const meta = updated ? `${summary} • ${updated}` : summary;
  return (
    <Pressable
      onPress={onPress}
      accessibilityRole="button"
      accessibilityLabel={title}
      style={({ pressed }) => [styles.card, pressed && styles.pressed]}
    >
      <View style={styles.iconSq}>
        <AppIcon icon={feather('file-text')} size={20} color={KN_TEAL} />
      </View>
      <View style={styles.copy}>
        <Text style={styles.title} numberOfLines={2}>
          {title}
        </Text>
        <Text style={styles.meta} numberOfLines={2}>
          {meta}
        </Text>
      </View>
      <AppIcon icon={feather('chevron-right')} size={18} color={KN_MUTED} />
    </Pressable>
  );
}

export function KnowledgeArticleCard({
  item,
  untitled,
  onPress,
  tr,
}: {
  item: KnowledgeItem;
  untitled: string;
  onPress: () => void;
  tr: (key: StringKey) => string;
}) {
  const summary = formatMediaSummary(countMedia(item.attachments));
  const stamp = formatUpdatedStamp(item.updated_at);
  const updated =
    stamp === 'today'
      ? tr('knowledgeUpdatedToday')
      : stamp
        ? tr('knowledgeUpdatedOn').replace('{date}', stamp)
        : '';
  return (
    <KnowledgeCard
      title={item.title.trim() || untitled}
      summary={summary === 'Text only' ? tr('knowledgeTextOnly') : summary}
      updated={updated}
      onPress={onPress}
    />
  );
}

export function KnowledgeLocationsCard({
  onPress,
  tr,
}: {
  onPress: () => void;
  tr: (key: StringKey) => string;
}) {
  return (
    <KnowledgeCard
      title={LOCATIONS_KNOWLEDGE_TITLE}
      summary={tr('knowledgeTextOnly')}
      updated=""
      onPress={onPress}
    />
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: KN_BORDER,
    borderWidth: 1,
    borderRadius: KN_RADIUS,
    padding: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
  },
  pressed: { opacity: 0.7 },
  iconSq: {
    width: KN_ICON_SQ,
    height: KN_ICON_SQ,
    borderRadius: 10,
    backgroundColor: KN_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 4 },
  title: {
    color: KN_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 16,
    fontWeight: '700',
  },
  meta: { color: KN_MUTED, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
});

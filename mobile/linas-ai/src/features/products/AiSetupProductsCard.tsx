import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing } from '../../theme';
import {
  AI_SETUP_CARD_BORDER,
  AI_SETUP_TEAL,
} from '../cm/aiSetupDesign';

type Props = {
  onOpenProducts: () => void;
};

/** AI Setup hub entry for tenant product catalog (Postgres-backed, not CM). */
export function AiSetupProductsCard({ onOpenProducts }: Props) {
  const { tr } = useI18n();

  return (
    <Pressable
      style={[styles.card, { borderColor: AI_SETUP_CARD_BORDER }]}
      onPress={onOpenProducts}
      accessibilityRole="button"
      accessibilityLabel={tr('productsTitle')}
    >
      <AppIcon icon={feather('package')} size={20} color={AI_SETUP_TEAL} />
      <View style={styles.text}>
        <Text style={styles.title}>{tr('productsTitle')}</Text>
        <Text style={styles.body}>{tr('productsHubDescription')}</Text>
      </View>
      <AppIcon icon={feather('chevron-right')} size={18} color={AI_SETUP_TEAL} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: spacing.sm,
    borderWidth: 1,
    borderRadius: radii.md,
    backgroundColor: '#FFFFFF',
    paddingHorizontal: 12,
    paddingVertical: 14,
  },
  text: { flex: 1, gap: 2 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 15, color: '#10221A' },
  body: { fontFamily: fonts.body, fontSize: 12, color: '#4A5C54', lineHeight: 16 },
});

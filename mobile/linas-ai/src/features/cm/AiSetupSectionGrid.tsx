import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { fonts, radii, spacing } from '../../theme';
import {
  AI_SETUP_CARD_BORDER,
  AI_SETUP_MISSING_BG,
  AI_SETUP_MISSING_BORDER,
  AI_SETUP_ORANGE,
  AI_SETUP_TEAL,
} from './aiSetupDesign';
import { CM_SECTION_ICONS } from './cmSectionIcons';
import { cmSectionTitleKey } from './cmSectionTitles';
import type { CmSectionCard } from './cmSections';

type Props = {
  tiles: CmSectionCard[];
  statusBySection: Map<string, 'complete' | 'incomplete'>;
  onOpenSection: (id: CmSectionCard['id']) => void;
};

/** Two-column section grid — complete (white) vs missing (peach) cards. */
export function AiSetupSectionGrid({ tiles, statusBySection, onOpenSection }: Props) {
  const { tr } = useI18n();

  return (
    <View style={styles.grid}>
      {tiles.map((tile) => {
        const supported = tile.mobileSupported !== false;
        const fill = statusBySection.get(tile.id);
        const missing = supported && fill !== 'complete';
        const title = tr(cmSectionTitleKey(tile.id));

        return (
          <Pressable
            key={tile.id}
            style={[
              styles.card,
              missing
                ? { backgroundColor: AI_SETUP_MISSING_BG, borderColor: AI_SETUP_MISSING_BORDER }
                : { backgroundColor: '#FFFFFF', borderColor: AI_SETUP_CARD_BORDER },
              { opacity: supported ? 1 : 0.55 },
            ]}
            disabled={!supported}
            onPress={() => supported && onOpenSection(tile.id)}
            accessibilityRole="button"
            accessibilityLabel={`${title}, ${missing ? tr('aiSetupStatusMissing') : tr('aiSetupStatusComplete')}`}
            accessibilityState={{ disabled: !supported }}
          >
            <AppIcon icon={CM_SECTION_ICONS[tile.id]} size={20} color={AI_SETUP_TEAL} />
            <Text style={styles.title} numberOfLines={2}>
              {title}
            </Text>
            {missing ? (
              <View style={styles.statusRow}>
                <View style={styles.orangeDot} />
                <Text style={styles.missingText}>{tr('aiSetupStatusMissing')}</Text>
              </View>
            ) : (
              <AppIcon icon={feather('check')} size={18} color={AI_SETUP_TEAL} />
            )}
          </Pressable>
        );
      })}
    </View>
  );
}

const styles = StyleSheet.create({
  grid: {
    flexDirection: 'row',
    flexWrap: 'wrap',
    gap: spacing.sm,
  },
  card: {
    flexGrow: 1,
    flexBasis: '47%',
    maxWidth: '48%',
    minHeight: 88,
    borderRadius: radii.md,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 14,
    flexDirection: 'row',
    alignItems: 'center',
    gap: 8,
  },
  title: {
    flex: 1,
    fontFamily: fonts.bodyMedium,
    fontSize: 14,
    color: '#10221A',
    lineHeight: 18,
  },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  orangeDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: AI_SETUP_ORANGE },
  missingText: { fontFamily: fonts.bodyMedium, fontSize: 11, color: AI_SETUP_ORANGE },
});

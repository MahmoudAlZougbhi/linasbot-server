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
import { resolveAiSetupSectionPaint } from './aiSetupSectionPaint';
import { CM_SECTION_ICONS } from './cmSectionIcons';
import { cmSectionTitleKey } from './cmSectionTitles';
import type { CmSectionCard } from './cmSections';

export type AiSetupTileVariant = 'full' | 'big' | 'small';

type SectionProps = {
  kind: 'section';
  tile: CmSectionCard;
  variant: AiSetupTileVariant;
  statusBySection: Map<string, 'complete' | 'incomplete'>;
  onPress: () => void;
};

type ProductsProps = {
  kind: 'products';
  variant: AiSetupTileVariant;
  onPress: () => void;
};

type Props = SectionProps | ProductsProps;

function tileChrome(
  paint: ReturnType<typeof resolveAiSetupSectionPaint>,
  supported: boolean,
) {
  const missing = supported && paint === 'missing';
  const complete = paint === 'complete';
  return {
    missing,
    complete,
    cardStyle: missing
      ? { backgroundColor: AI_SETUP_MISSING_BG, borderColor: AI_SETUP_MISSING_BORDER }
      : { backgroundColor: '#FFFFFF', borderColor: AI_SETUP_CARD_BORDER },
    opacity: supported ? 1 : 0.55,
  };
}

function StatusBadge({
  missing,
  complete,
}: {
  missing: boolean;
  complete: boolean;
}) {
  const { tr } = useI18n();
  if (missing) {
    return (
      <View style={styles.statusRow}>
        <View style={styles.orangeDot} />
        <Text style={styles.missingText}>{tr('aiSetupStatusMissing')}</Text>
      </View>
    );
  }
  if (complete) {
    return <AppIcon icon={feather('check')} size={18} color={AI_SETUP_TEAL} />;
  }
  return null;
}

export function AiSetupSectionTile(props: Props) {
  const { tr } = useI18n();
  const { variant, onPress } = props;

  if (props.kind === 'products') {
    return (
      <Pressable
        style={[styles.base, styles[variant], { borderColor: AI_SETUP_CARD_BORDER, backgroundColor: '#FFFFFF' }]}
        onPress={onPress}
        accessibilityRole="button"
        accessibilityLabel={tr('productsTitle')}
      >
        <AppIcon icon={feather('package')} size={variant === 'small' ? 18 : 20} color={AI_SETUP_TEAL} />
        <View style={styles.textBlock}>
          <Text style={[styles.title, variant === 'small' && styles.titleSmall]} numberOfLines={variant === 'full' ? 1 : 2}>
            {tr('productsTitle')}
          </Text>
          {variant === 'full' || variant === 'big' ? (
            <Text style={styles.body} numberOfLines={variant === 'big' ? 2 : 1}>
              {tr('productsHubDescription')}
            </Text>
          ) : null}
        </View>
        {variant === 'full' ? <AppIcon icon={feather('chevron-right')} size={18} color={AI_SETUP_TEAL} /> : null}
      </Pressable>
    );
  }

  const { tile, statusBySection } = props;
  const supported = tile.mobileSupported !== false;
  const paint = resolveAiSetupSectionPaint(statusBySection.get(tile.id));
  const { missing, complete, cardStyle, opacity } = tileChrome(paint, supported);
  const title = tr(cmSectionTitleKey(tile.id));
  const statusLabel =
    paint === 'pending'
      ? title
      : `${title}, ${missing ? tr('aiSetupStatusMissing') : tr('aiSetupStatusComplete')}`;

  return (
    <Pressable
      style={[styles.base, styles[variant], cardStyle, { opacity }]}
      disabled={!supported}
      onPress={() => supported && onPress()}
      accessibilityRole="button"
      accessibilityLabel={statusLabel}
      accessibilityState={{ disabled: !supported }}
    >
      <AppIcon icon={CM_SECTION_ICONS[tile.id]} size={variant === 'small' ? 18 : 20} color={AI_SETUP_TEAL} />
      <View style={styles.textBlock}>
        <Text style={[styles.title, variant === 'small' && styles.titleSmall]} numberOfLines={variant === 'full' ? 1 : 2}>
          {title}
        </Text>
        {variant === 'full' || variant === 'big' ? (
          <Text style={styles.body} numberOfLines={variant === 'big' ? 2 : 1}>
            {tile.description}
          </Text>
        ) : null}
      </View>
      <StatusBadge missing={missing} complete={complete} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  base: {
    borderWidth: 1,
    borderRadius: radii.md,
    gap: spacing.sm,
  },
  full: {
    width: '100%',
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 12,
    paddingVertical: 14,
  },
  big: {
    flex: 1.15,
    minHeight: 132,
    paddingHorizontal: 12,
    paddingVertical: 14,
    justifyContent: 'space-between',
  },
  small: {
    flex: 1,
    minHeight: 62,
    flexDirection: 'row',
    alignItems: 'center',
    paddingHorizontal: 10,
    paddingVertical: 10,
    gap: 8,
  },
  textBlock: { flex: 1, gap: 2 },
  title: { fontFamily: fonts.bodyMedium, fontSize: 15, color: '#10221A', lineHeight: 19 },
  titleSmall: { fontSize: 13, lineHeight: 17 },
  body: { fontFamily: fonts.body, fontSize: 12, color: '#4A5C54', lineHeight: 16 },
  statusRow: { flexDirection: 'row', alignItems: 'center', gap: 4 },
  orangeDot: { width: 7, height: 7, borderRadius: 4, backgroundColor: AI_SETUP_ORANGE },
  missingText: { fontFamily: fonts.bodyMedium, fontSize: 11, color: AI_SETUP_ORANGE },
});

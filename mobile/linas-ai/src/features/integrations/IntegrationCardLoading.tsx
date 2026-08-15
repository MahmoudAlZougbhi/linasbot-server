import { StyleSheet, View } from 'react-native';

import { colors, spacing } from '../../theme';
import {
  IntegrationPlatformIcon,
  type IntegrationPlatform,
} from './IntegrationPlatformIcon';

type Props = {
  platform: IntegrationPlatform;
};

/** Neutral placeholder while integration card data is still loading. */
export function IntegrationCardLoading({ platform }: Props) {
  return (
    <View style={styles.card} accessibilityRole="progressbar">
      <View style={styles.head}>
        <IntegrationPlatformIcon platform={platform} size={48} />
        <View style={styles.meta}>
          <View style={[styles.line, styles.titleLine]} />
          <View style={[styles.line, styles.subtitleLine]} />
          <View style={[styles.line, styles.pillLine]} />
        </View>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.surface,
    borderRadius: 14,
    padding: spacing.lg,
    marginBottom: spacing.md,
    shadowColor: '#10221A',
    shadowOffset: { width: 0, height: 2 },
    shadowOpacity: 0.07,
    shadowRadius: 10,
    elevation: 3,
  },
  head: {
    flexDirection: 'row',
    gap: spacing.md,
    alignItems: 'flex-start',
  },
  meta: { flex: 1, gap: 8, minWidth: 0 },
  line: {
    borderRadius: 6,
    backgroundColor: '#E8ECEB',
  },
  titleLine: { height: 16, width: '46%' },
  subtitleLine: { height: 12, width: '68%' },
  pillLine: { height: 20, width: 88, borderRadius: 999, marginTop: 2 },
});

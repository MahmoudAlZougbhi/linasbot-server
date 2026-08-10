import { StyleSheet, View } from 'react-native';

import { useI18n } from '../../i18n/LanguageContext';

/**
 * Quiet canvas while New Chat create resolves.
 * Owner conversations always seed a greeting message; a typewriter here would
 * type then vanish when that bubble arrives. The greeting types in the bubble.
 */
export function OwnerEmptyState() {
  const { tr } = useI18n();
  const title = tr('chatEmptyTitle');
  const body = tr('chatEmptyBody');

  return (
    <View
      style={styles.wrap}
      accessibilityLabel={`${title}. ${body}`}
      accessible
    />
  );
}

const styles = StyleSheet.create({
  wrap: { padding: 24, minHeight: 48 },
});

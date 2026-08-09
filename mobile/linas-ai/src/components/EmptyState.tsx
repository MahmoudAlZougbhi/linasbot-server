import { StyleSheet, Text, View } from 'react-native';

import { LinasStarMark } from './LinasStarMark';
import { fonts, typography, useTheme } from '../theme';

type Props = {
  title: string;
  body?: string;
  /** Ignored — mascot/character assets are forbidden. */
  showMascot?: boolean;
};

export function EmptyState({ title, body }: Props) {
  const { colors } = useTheme();
  return (
    <View style={styles.wrap}>
      <LinasStarMark size={36} />
      <Text style={[styles.title, { color: colors.text }]}>{title}</Text>
      {body ? <Text style={[styles.body, { color: colors.textMuted }]}>{body}</Text> : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { paddingVertical: 40, paddingHorizontal: 28, alignItems: 'center' },
  title: {
    ...typography.bodyStrong,
    fontFamily: fonts.bodyMedium,
    textAlign: 'center',
    marginTop: 12,
  },
  body: {
    ...typography.caption,
    textAlign: 'center',
    marginTop: 8,
    maxWidth: 280,
  },
});

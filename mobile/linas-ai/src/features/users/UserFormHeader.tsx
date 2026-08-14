import { Pressable, StyleSheet, Text, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';

import { AppIcon, feather } from '../../components/AppIcon';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, HIT, spacing } from '../../theme';

type Props = {
  title: string;
  subtitle: string;
  onBack: () => void;
};

export function UserFormHeader({ title, subtitle, onBack }: Props) {
  const insets = useSafeAreaInsets();
  const { tr } = useI18n();
  return (
    <View style={[styles.top, { paddingTop: insets.top + 8 }]}>
      <View style={styles.row}>
        <Pressable
          onPress={onBack}
          accessibilityRole="button"
          accessibilityLabel={tr('back')}
          style={({ pressed }) => [styles.hit, pressed && styles.pressed]}
        >
          <AppIcon icon={feather('chevron-left')} size={26} color={colors.text} />
        </Pressable>
        <View style={styles.titles}>
          <Text style={styles.title}>{title}</Text>
          <Text style={styles.sub}>{subtitle}</Text>
        </View>
        <View style={styles.hit} />
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  top: { paddingHorizontal: spacing.md, paddingBottom: spacing.md },
  row: { flexDirection: 'row', alignItems: 'center' },
  hit: { width: HIT, height: HIT, alignItems: 'center', justifyContent: 'center' },
  titles: { flex: 1, alignItems: 'center' },
  title: { fontFamily: fonts.bodyMedium, fontSize: 18, fontWeight: '700', color: colors.text },
  sub: { fontFamily: fonts.body, fontSize: 13, color: colors.textMuted, marginTop: 3 },
  pressed: { opacity: 0.55 },
});

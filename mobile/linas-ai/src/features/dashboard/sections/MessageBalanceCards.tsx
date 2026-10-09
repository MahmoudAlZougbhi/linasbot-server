import { Pressable, StyleSheet, Text, View } from 'react-native';

import { fonts, spacing } from '../../../theme';

type Props = {
  planRemaining: number | null;
  planUsed: number | null;
  planExpires: string | null;
  planExpired: boolean;
  purchasedRemaining: number | null;
  purchasedUsed: number | null;
  onBuyMore: () => void;
};

export function MessageBalanceCards({
  planRemaining,
  planUsed,
  planExpires,
  planExpired,
  purchasedRemaining,
  purchasedUsed,
  onBuyMore,
}: Props) {
  return (
    <View style={styles.wrap}>
      <View style={styles.card}>
        <Text style={styles.title}>Plan messages</Text>
        {planExpired ? (
          <Text style={styles.body}>Expired. Renew to get messages.</Text>
        ) : (
          <Text style={styles.body}>
            {planRemaining == null ? 'Not loaded yet' : `${planRemaining} left`}
            {planUsed == null ? '' : ` · used ${planUsed}`}
            {planExpires ? ` · expires ${planExpires}` : ''}
          </Text>
        )}
      </View>
      <View style={styles.card}>
        <Text style={styles.title}>Purchased messages</Text>
        <Text style={styles.body}>
          {purchasedRemaining == null ? 'Not loaded yet' : `${purchasedRemaining} left`}
          {' · never expire'}
          {purchasedUsed == null ? '' : ` · used ${purchasedUsed}`}
        </Text>
        <Pressable accessibilityRole="button" onPress={onBuyMore}>
          <Text style={styles.link}>Buy more</Text>
        </Pressable>
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm },
  card: { backgroundColor: '#fff', borderRadius: 12, padding: spacing.md },
  title: { fontFamily: fonts.bodyMedium, fontSize: 16 },
  body: { marginTop: 4, fontFamily: fonts.body, fontSize: 14 },
  link: { marginTop: 8, fontFamily: fonts.bodyMedium, color: '#0F766E' },
});

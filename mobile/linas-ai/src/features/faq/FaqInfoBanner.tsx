import { StyleSheet, Text, View } from 'react-native';

import { LinasSparkleIcon } from '../../components/LinasSparkleIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { FAQ_INFO_BG, FAQ_INFO_BORDER, FAQ_PAD, FAQ_RADIUS, FAQ_TEAL, FAQ_TEXT } from './faqChrome';

type Props = {
  upgradeMessage?: string | null;
  tr: (key: StringKey) => string;
};

export function FaqInfoBanner({ upgradeMessage, tr }: Props) {
  return (
    <View style={styles.card}>
      <LinasSparkleIcon size={22} color={FAQ_TEAL} />
      <View style={styles.copy}>
        <Text style={styles.title}>{tr('faqWhyTitle')}</Text>
        <Text style={styles.body}>{tr('faqWhyBody')}</Text>
        {upgradeMessage ? <Text style={styles.warn}>{upgradeMessage}</Text> : null}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: FAQ_INFO_BG,
    borderColor: FAQ_INFO_BORDER,
    borderWidth: 1,
    borderRadius: FAQ_RADIUS,
    padding: FAQ_PAD,
    flexDirection: 'row',
    alignItems: 'flex-start',
    gap: 12,
  },
  copy: { flex: 1, gap: 4 },
  title: {
    color: FAQ_TEXT,
    fontFamily: fonts.bodyMedium,
    fontSize: 15,
    fontWeight: '700',
  },
  body: {
    color: '#64748B',
    fontFamily: fonts.body,
    fontSize: 13,
    lineHeight: 19,
  },
  warn: { color: '#DC2626', fontFamily: fonts.body, fontSize: 12, marginTop: 4 },
});

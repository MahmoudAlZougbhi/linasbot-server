import { Pressable, StyleSheet, Text, View } from 'react-native';

import { AppIcon, feather } from '../../components/AppIcon';
import type { StringKey } from '../../i18n';
import { fonts } from '../../theme';
import { FAQ_BORDER, FAQ_PAD, FAQ_RADIUS, FAQ_TEAL, FAQ_TEXT } from './faqChrome';
import { langNativeLabel } from './faqLanguages';

type Props = {
  languages: string[];
  previewLang: string;
  onPreviewLang: (langId: string) => void;
  onAddLanguage: () => void;
  onRemoveLanguage: (langId: string) => void;
  tr: (key: StringKey) => string;
};

export function FaqLanguagesCard({
  languages,
  previewLang,
  onPreviewLang,
  onAddLanguage,
  onRemoveLanguage,
  tr,
}: Props) {
  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>{tr('faqLangSection')}</Text>
        <Pressable onPress={onAddLanguage} style={styles.addBtn} accessibilityRole="button">
          <AppIcon icon={feather('plus')} size={12} color={FAQ_TEAL} />
          <Text style={styles.addText}>{tr('faqAddLanguage')}</Text>
        </Pressable>
      </View>
      <Text style={styles.hint}>{tr('faqLangHint')}</Text>
      <View style={styles.chips}>
        {languages.map((langId) => {
          const on = langId === previewLang;
          return (
            <Pressable
              key={langId}
              onPress={() => onPreviewLang(langId)}
              style={[styles.chip, on ? styles.chipOn : styles.chipOff]}
              accessibilityRole="button"
              accessibilityState={{ selected: on }}
            >
              <Text style={[styles.chipText, on ? styles.chipTextOn : styles.chipTextOff]}>
                {langNativeLabel(langId)}
              </Text>
              <Pressable
                onPress={() => onRemoveLanguage(langId)}
                hitSlop={6}
                accessibilityRole="button"
                accessibilityLabel={`${tr('faqRemoveLanguage')} ${langNativeLabel(langId)}`}
              >
                <Text style={[styles.chipX, on ? styles.chipXOn : styles.chipXOff]}>×</Text>
              </Pressable>
            </Pressable>
          );
        })}
      </View>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: '#FFFFFF',
    borderColor: FAQ_BORDER,
    borderWidth: 1,
    borderRadius: FAQ_RADIUS,
    padding: FAQ_PAD,
    gap: 10,
  },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 8 },
  title: { color: FAQ_TEXT, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700', flex: 1 },
  addBtn: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 4,
    borderWidth: 1,
    borderColor: FAQ_TEAL,
    borderRadius: 999,
    paddingHorizontal: 10,
    paddingVertical: 5,
  },
  addText: { color: FAQ_TEAL, fontFamily: fonts.bodyMedium, fontSize: 12 },
  hint: { color: '#94A3B8', fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  chip: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 6,
    borderRadius: 999,
    borderWidth: 1,
    paddingHorizontal: 12,
    paddingVertical: 6,
  },
  chipOn: { backgroundColor: FAQ_TEAL, borderColor: FAQ_TEAL },
  chipOff: { backgroundColor: '#FFFFFF', borderColor: FAQ_TEAL },
  chipText: { fontFamily: fonts.body, fontSize: 13 },
  chipTextOn: { color: '#FFFFFF' },
  chipTextOff: { color: FAQ_TEXT },
  chipX: { fontSize: 15, lineHeight: 16 },
  chipXOn: { color: '#FFFFFF' },
  chipXOff: { color: FAQ_TEAL },
});

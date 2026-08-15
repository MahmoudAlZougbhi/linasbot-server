import React from 'react';
import { Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppModal } from '../../components/AppModal';
import { ModalScrim } from '../../components/ModalScrim';

import { PrimaryButton } from '../../components/PrimaryButton';
import type { StringKey } from '../../i18n';
import { colors, fonts, radii, spacing } from '../../theme';
import type { SmartAnswerLang } from './faqLanguages';
import { getSmartAnswerLanguageCatalog } from './faqLanguages';

type Props = {
  visible: boolean;
  selected: string[];
  catalog?: SmartAnswerLang[];
  saving: boolean;
  onClose: () => void;
  onSave: (languages: string[]) => void;
  tr: (key: StringKey) => string;
};

export function FaqLanguagePickerModal({ visible, selected, catalog, saving, onClose, onSave, tr }: Props) {
  const [draft, setDraft] = React.useState<string[]>(selected);
  const [query, setQuery] = React.useState('');
  const languageCatalog = catalog?.length ? catalog : getSmartAnswerLanguageCatalog();

  React.useEffect(() => {
    if (visible) {
      setDraft(selected);
      setQuery('');
    }
  }, [visible, selected]);

  const filtered = languageCatalog.filter((lang) => {
    const q = query.trim().toLowerCase();
    if (!q) return true;
    return (
      lang.id.includes(q) ||
      lang.label.toLowerCase().includes(q) ||
      (lang.native || '').toLowerCase().includes(q)
    );
  });

  const toggle = (id: string) => {
    setDraft((prev) => {
      if (prev.includes(id)) {
        const next = prev.filter((x) => x !== id);
        return next.length ? next : prev;
      }
      return [...prev, id];
    });
  };

  return (
    <AppModal visible={visible} animationType="slide" onRequestClose={onClose}>
      <ModalScrim onPress={onClose}>
        <View style={styles.sheet}>
          <View style={styles.handle} />
          <View style={styles.header}>
            <Text style={styles.title}>{tr('faqLangPickerTitle')}</Text>
            <Pressable onPress={onClose} hitSlop={8}>
              <Text style={styles.close}>✕</Text>
            </Pressable>
          </View>
          <Text style={styles.sub}>{tr('faqLangPickerSub')}</Text>
          <TextInput
            value={query}
            onChangeText={setQuery}
            placeholder={tr('faqLangSearch')}
            placeholderTextColor={colors.textMuted}
            style={styles.search}
          />
          <Text style={styles.count}>
            {draft.length} {tr('faqLangSelected')}
          </Text>
          <ScrollView style={styles.list}>
            {filtered.map((lang) => {
              const on = draft.includes(lang.id);
              return (
                <Pressable key={lang.id} style={styles.row} onPress={() => toggle(lang.id)}>
                  <View style={[styles.check, on ? styles.checkOn : null]}>
                    {on ? <Text style={styles.checkMark}>✓</Text> : null}
                  </View>
                  <View style={{ flex: 1 }}>
                    <Text style={styles.rowLabel}>{lang.label}</Text>
                    {lang.native ? <Text style={styles.rowNative}>{lang.native}</Text> : null}
                  </View>
                </Pressable>
              );
            })}
          </ScrollView>
          <Text style={styles.footer}>{tr('faqLangAutoTranslate')}</Text>
          <PrimaryButton label={tr('faqLangSave')} onPress={() => onSave(draft)} loading={saving} />
        </View>
      </ModalScrim>
    </AppModal>
  );
}

const styles = StyleSheet.create({
  sheet: {
    backgroundColor: colors.bg,
    borderTopLeftRadius: 20,
    borderTopRightRadius: 20,
    padding: spacing.lg,
    maxHeight: '82%',
    gap: spacing.sm,
  },
  handle: {
    alignSelf: 'center',
    width: 40,
    height: 4,
    borderRadius: 2,
    backgroundColor: colors.border,
    marginBottom: spacing.xs,
  },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 18 },
  close: { color: colors.textDim, fontSize: 18 },
  sub: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  search: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    borderWidth: 1,
    borderColor: colors.border,
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 14,
    paddingHorizontal: spacing.md,
    paddingVertical: 10,
  },
  count: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
  list: { maxHeight: 320 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 12, paddingVertical: 10 },
  check: {
    width: 22,
    height: 22,
    borderRadius: 11,
    borderWidth: 1,
    borderColor: colors.border,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkOn: { backgroundColor: colors.accent, borderColor: colors.accent },
  checkMark: { color: colors.bg, fontSize: 12, fontFamily: fonts.bodyMedium },
  rowLabel: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  rowNative: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
  footer: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12, textAlign: 'center' },
});

import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';

import { ApiError } from '../../api/client';
import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, radii, spacing } from '../../theme';
import { ScreenChrome } from '../shared/ScreenChrome';
import { createFaq, listFaq, type FaqGroup } from './faqApi';
import { Field } from '../cm/editors/Field';

type Props = {
  onBack: () => void;
};

export function FaqScreen({ onBack }: Props) {
  const { tr } = useI18n();
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [items, setItems] = useState<FaqGroup[]>([]);
  const [mode, setMode] = useState<'list' | 'create'>('list');
  const [question, setQuestion] = useState('');
  const [answer, setAnswer] = useState('');
  const [savedFlash, setSavedFlash] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listFaq();
      setItems(data);
    } catch (err) {
      const msg =
        err instanceof ApiError
          ? err.message
          : tr('faqLoadError');
      setError(msg);
    } finally {
      setLoading(false);
    }
  }, [tr]);

  useEffect(() => {
    void load();
  }, [load]);

  async function handleCreate() {
    const q = question.trim();
    const a = answer.trim();
    if (!q || !a) {
      setError(tr('likeFaqNeedBoth'));
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await createFaq({ question: q, answer: a, language: 'en' });
      setQuestion('');
      setAnswer('');
      setMode('list');
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2500);
      await load();
    } catch (err) {
      if (err instanceof ApiError && err.status === 402) {
        setError(tr('faqQuotaUpgrade'));
      } else {
        setError(err instanceof ApiError ? err.message : tr('faqCreateError'));
      }
    } finally {
      setSaving(false);
    }
  }

  function enPreview(group: FaqGroup): string {
    const variants = Array.isArray(group.variants) ? group.variants : [];
    const en = variants.find((v) => String(v.language) === 'en');
    if (en && typeof en.question === 'string' && en.question.trim()) return en.question.trim();
    const any = variants.find((v) => typeof v.question === 'string' && String(v.question).trim());
    return any ? String(any.question) : String(group.qa_group_id || 'FAQ');
  }

  return (
    <ScreenChrome title={tr('faqTitle')} subtitle={tr('faqSub')} onBack={onBack}>
      {loading ? <ActivityIndicator color={colors.accent} /> : null}
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {savedFlash ? <Text style={styles.ok}>{tr('faqSaved')}</Text> : null}

      {mode === 'list' ? (
        <ScrollView contentContainerStyle={styles.list}>
          <PrimaryButton label={tr('faqCreateNew')} onPress={() => setMode('create')} />
          <Text style={styles.section}>{tr('faqSavedList')}</Text>
          {items.length === 0 && !loading ? (
            <Text style={styles.hint}>{tr('faqEmpty')}</Text>
          ) : null}
          {items.map((item) => (
            <View key={String(item.qa_group_id)} style={styles.card}>
              <Text style={styles.title}>{enPreview(item)}</Text>
              <Text style={styles.sub}>{String(item.status || 'draft')}</Text>
            </View>
          ))}
          <PrimaryButton label={tr('retry')} variant="ghost" onPress={() => void load()} />
        </ScrollView>
      ) : (
        <ScrollView contentContainerStyle={styles.list}>
          <Text style={styles.hint}>{tr('faqCreateHint')}</Text>
          <View style={styles.card}>
            <Field label={tr('likeFaqQuestion')} value={question} onChange={setQuestion} multiline />
            <Field label={tr('likeFaqAnswer')} value={answer} onChange={setAnswer} multiline />
          </View>
          <View style={styles.actions}>
            <PrimaryButton
              label={tr('likeFaqSave')}
              onPress={() => void handleCreate()}
              loading={saving}
              style={{ flex: 1 }}
            />
            <PrimaryButton
              label={tr('usersCancel')}
              variant="ghost"
              onPress={() => setMode('list')}
              style={{ flex: 1 }}
            />
          </View>
        </ScrollView>
      )}
    </ScreenChrome>
  );
}

const styles = StyleSheet.create({
  list: { paddingBottom: 40, gap: spacing.md },
  section: {
    color: colors.textDim,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    letterSpacing: 0.8,
    textTransform: 'uppercase',
    marginTop: spacing.md,
  },
  card: {
    backgroundColor: colors.surface,
    borderRadius: radii.lg,
    padding: spacing.lg,
    borderWidth: 1,
    borderColor: colors.border,
  },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15 },
  sub: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12, marginTop: 4 },
  hint: { color: colors.textDim, fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  error: { color: colors.danger, fontFamily: fonts.body, marginBottom: spacing.sm },
  ok: { color: colors.success, fontFamily: fonts.body, marginBottom: spacing.sm },
  actions: { flexDirection: 'row', gap: 8 },
});

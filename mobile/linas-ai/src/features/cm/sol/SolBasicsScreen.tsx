import { useState } from 'react';
import { ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';

import { PrimaryButton } from '../../../components/PrimaryButton';
import { ScreenSkeleton } from '../../../components/ScreenSkeleton';
import { useI18n } from '../../../i18n/LanguageContext';
import { fonts } from '../../../theme';
import { ScreenChrome } from '../../shared/ScreenChrome';
import type { CmProposalReview } from '../cmProposalReview';
import { cmFormStyles } from '../cmFormStyles';
import { useCmDraft } from '../useCmDraft';

type Props = {
  proposalReview?: CmProposalReview | null;
  onBack?: () => void;
};

function asList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((row) => String(row ?? '').trim()).filter(Boolean);
}

function str(payload: Record<string, unknown>, key: string): string {
  const v = payload[key];
  return typeof v === 'string' ? v : v == null ? '' : String(v);
}

export function SolBasicsScreen({ proposalReview, onBack }: Props) {
  const { tr } = useI18n();
  const draft = useCmDraft('sol_basics', proposalReview);
  const [savedFlash, setSavedFlash] = useState(false);
  const payload = draft.payload;

  function set(key: string, value: string) {
    draft.setPayload({ ...payload, [key]: value });
  }

  function setList(key: string, raw: string) {
    draft.setPayload({
      ...payload,
      [key]: raw
        .split('\n')
        .map((line) => line.trim())
        .filter(Boolean),
    });
  }

  async function handleSave() {
    const ok = await draft.save();
    if (ok) {
      setSavedFlash(true);
      setTimeout(() => setSavedFlash(false), 2000);
    }
  }

  return (
    <ScreenChrome title="Sol" subtitle="Owner AI identity. Save publishes Live for Sol chat." onBack={onBack}>
      {draft.loading ? <ScreenSkeleton variant="form" /> : null}
      {draft.error ? <Text style={cmFormStyles.error}>{draft.error}</Text> : null}
      {draft.conflict ? <Text style={cmFormStyles.warn}>{draft.conflict}</Text> : null}
      {savedFlash ? <Text style={cmFormStyles.ok}>{tr('aiSetupDraftSaved')}</Text> : null}
      {!draft.loading ? (
        <ScrollView contentContainerStyle={{ paddingBottom: 48 }}>
          <Labeled field="Name" value={str(payload, 'assistant_name')} onChange={(v) => set('assistant_name', v)} />
          <Area field="Role" value={str(payload, 'ai_role')} onChange={(v) => set('ai_role', v)} />
          <Area field="Tone" value={str(payload, 'tone')} onChange={(v) => set('tone', v)} />
          <Area
            field="Identity summary"
            value={str(payload, 'identity_summary')}
            onChange={(v) => set('identity_summary', v)}
          />
          <Area field="Reply style" value={str(payload, 'reply_style')} onChange={(v) => set('reply_style', v)} />
          <Area
            field="Advanced instructions"
            value={str(payload, 'advanced_instructions')}
            onChange={(v) => set('advanced_instructions', v)}
          />
          <Area
            field="Do (one per line)"
            value={asList(payload.do_list).join('\n')}
            onChange={(v) => setList('do_list', v)}
          />
          <Area
            field="Don't (one per line)"
            value={asList(payload.dont_list).join('\n')}
            onChange={(v) => setList('dont_list', v)}
          />
          <View style={cmFormStyles.actions}>
            <PrimaryButton
              label={draft.dirty ? tr('aiSetupSaveDraft') : tr('aiSetupSaved')}
              onPress={() => void handleSave()}
              loading={draft.saving}
              disabled={!draft.dirty || !draft.etag}
              style={{ flex: 1 }}
            />
            <PrimaryButton
              label={tr('aiSetupReload')}
              variant="ghost"
              onPress={() => void draft.load()}
              style={{ flex: 1 }}
            />
          </View>
        </ScrollView>
      ) : null}
    </ScreenChrome>
  );
}

function Labeled({ field, value, onChange }: { field: string; value: string; onChange: (v: string) => void }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{field}</Text>
      <TextInput value={value} onChangeText={onChange} style={styles.input} />
    </View>
  );
}

function Area({ field, value, onChange }: { field: string; value: string; onChange: (v: string) => void }) {
  return (
    <View style={styles.field}>
      <Text style={styles.label}>{field}</Text>
      <TextInput value={value} onChangeText={onChange} style={styles.area} multiline />
    </View>
  );
}

const styles = StyleSheet.create({
  field: { marginBottom: 12 },
  label: { fontFamily: fonts.bodyMedium, fontSize: 12, marginBottom: 6 },
  input: {
    fontFamily: fonts.body,
    fontSize: 15,
    borderWidth: 1,
    borderColor: '#D1D5DB',
    borderRadius: 10,
    paddingHorizontal: 12,
    minHeight: 44,
  },
  area: {
    fontFamily: fonts.body,
    fontSize: 14,
    borderWidth: 1,
    borderColor: '#D1D5DB',
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    minHeight: 96,
    textAlignVertical: 'top',
  },
});

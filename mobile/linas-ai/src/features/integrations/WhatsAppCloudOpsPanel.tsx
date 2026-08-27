import { useCallback, useEffect, useState } from 'react';
import { StyleSheet, Text, TextInput, View } from 'react-native';

import { PrimaryButton } from '../../components/PrimaryButton';
import { useI18n } from '../../i18n/LanguageContext';
import { colors, fonts, spacing } from '../../theme';
import {
  isWhatsAppAppReviewTest,
  normalizeWhatsAppRecipient,
  whatsappApiErrorDetail,
} from './whatsappCloudPresentation';
import {
  createWhatsAppTemplate,
  listWhatsAppConversations,
  pauseWhatsAppConversation,
  resumeWhatsAppConversation,
  sendWhatsAppTestMessage,
  type WhatsAppConversationRow,
} from './whatsappCloudApi';

type Props = {
  connectionId: string;
  connectionSource?: 'embedded_signup' | 'meta_app_review_test';
  busy?: boolean;
  onBusyChange?: (busy: boolean) => void;
  onError?: (message: string | null) => void;
  onNotice?: (message: string) => void;
};

/** App Review filming surfaces: real test send, template create, pause/resume. */
export function WhatsAppCloudOpsPanel({
  connectionId,
  connectionSource,
  busy,
  onBusyChange,
  onError,
  onNotice,
}: Props) {
  const { tr } = useI18n();
  const [toWaId, setToWaId] = useState('');
  const [testText, setTestText] = useState('Hello from Linas AI WhatsApp Cloud test');
  const [tplName, setTplName] = useState('linas_ai_utility_hello');
  const [tplBody, setTplBody] = useState('Hello {{1}}, this is a Linas AI WhatsApp utility template.');
  const [conversations, setConversations] = useState<WhatsAppConversationRow[]>([]);
  const [loadingConv, setLoadingConv] = useState(false);
  const appReviewTest = isWhatsAppAppReviewTest({ connection_source: connectionSource });

  const loadConversations = useCallback(async () => {
    setLoadingConv(true);
    try {
      const rows = await listWhatsAppConversations(connectionId);
      setConversations(rows);
    } catch {
      setConversations([]);
    } finally {
      setLoadingConv(false);
    }
  }, [connectionId]);

  useEffect(() => {
    if (appReviewTest) return;
    void loadConversations();
  }, [appReviewTest, loadConversations]);

  async function run(action: () => Promise<void>) {
    onBusyChange?.(true);
    onError?.(null);
    try {
      await action();
    } catch (err) {
      onError?.(whatsappApiErrorDetail(err) || tr('integrationsActionError'));
    } finally {
      onBusyChange?.(false);
    }
  }

  return (
    <View style={styles.wrap}>
      <Text style={styles.section}>{tr('waTestMessageTitle')}</Text>
      <Text style={styles.hint}>{tr('waTestMessageHint')}</Text>
      <TextInput
        style={styles.input}
        value={toWaId}
        onChangeText={setToWaId}
        placeholder={tr('waTestToPlaceholder')}
        placeholderTextColor={colors.textDim}
        keyboardType="phone-pad"
        autoCapitalize="none"
      />
      <TextInput
        style={[styles.input, styles.multiline]}
        value={testText}
        onChangeText={setTestText}
        placeholder={tr('waTestTextPlaceholder')}
        placeholderTextColor={colors.textDim}
        multiline
      />
      <PrimaryButton
        label={tr('waSendTestMessage')}
        loading={busy}
        onPress={() =>
          void run(async () => {
            const recipient = normalizeWhatsAppRecipient(toWaId);
            if (!recipient) throw new Error(tr('waTestRecipientInvalid'));
            const message = testText.trim();
            if (!message) throw new Error(tr('waTestTextInvalid'));
            setToWaId(recipient);
            const res = await sendWhatsAppTestMessage(connectionId, recipient, message);
            onNotice?.(
              res.provider_wamid
                ? `${tr('waTestMessageSent')} (${res.provider_wamid})`
                : tr('waTestMessageSent'),
            );
          })
        }
      />

      {appReviewTest ? <Text style={styles.hint}>{tr('waTestReplyHint')}</Text> : null}

      {!appReviewTest ? (
        <>
          <Text style={styles.section}>{tr('waTemplateTitle')}</Text>
          <Text style={styles.hint}>{tr('waTemplateHint')}</Text>
          <TextInput
            style={styles.input}
            value={tplName}
            onChangeText={setTplName}
            placeholder={tr('waTemplateNamePlaceholder')}
            placeholderTextColor={colors.textDim}
            autoCapitalize="none"
          />
          <TextInput
            style={[styles.input, styles.multiline]}
            value={tplBody}
            onChangeText={setTplBody}
            placeholder={tr('waTemplateBodyPlaceholder')}
            placeholderTextColor={colors.textDim}
            multiline
          />
          <PrimaryButton
            label={tr('waCreateTemplate')}
            loading={busy}
            variant="ghost"
            onPress={() =>
              void run(async () => {
                const res = await createWhatsAppTemplate(connectionId, {
                  name: tplName.trim(),
                  body_text: tplBody.trim(),
                  language: 'en_US',
                  category: 'UTILITY',
                });
                const status = res.template?.status || 'submitted';
                onNotice?.(`${tr('waTemplateCreated')}: ${status}`);
              })
            }
          />

          <Text style={styles.section}>{tr('waConversationsTitle')}</Text>
          <Text style={styles.hint}>{tr('waConversationsHint')}</Text>
          <PrimaryButton
            label={tr('waRefreshConversations')}
            loading={loadingConv}
            variant="ghost"
            onPress={() => void loadConversations()}
          />
          {conversations.length === 0 ? (
            <Text style={styles.meta}>{tr('waNoConversations')}</Text>
          ) : (
            conversations.map((c) => {
              const paused = c.control_state === 'HUMAN_PAUSED';
              const label = c.customer_profile_name || c.customer_wa_id_masked || c.conversation_id;
              return (
                <View key={c.conversation_id} style={styles.convRow}>
                  <Text style={styles.meta}>
                    {label} · {paused ? tr('waAiPaused') : tr('waAiActive')}
                    {c.pause_reason ? ` (${c.pause_reason})` : ''}
                  </Text>
                  {paused ? (
                    <PrimaryButton
                      label={tr('waResumeAi')}
                      variant="ghost"
                      loading={busy}
                      onPress={() =>
                        void run(async () => {
                          await resumeWhatsAppConversation(c.conversation_id);
                          onNotice?.(tr('waResumeAiDone'));
                          await loadConversations();
                        })
                      }
                    />
                  ) : (
                    <PrimaryButton
                      label={tr('waPauseAi')}
                      variant="ghost"
                      loading={busy}
                      onPress={() =>
                        void run(async () => {
                          await pauseWhatsAppConversation(c.conversation_id);
                          onNotice?.(tr('waPauseAiDone'));
                          await loadConversations();
                        })
                      }
                    />
                  )}
                </View>
              );
            })
          )}
        </>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: spacing.sm, marginTop: spacing.md },
  section: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 15, marginTop: spacing.sm },
  hint: { color: colors.textMuted, fontSize: 12, lineHeight: 17 },
  input: {
    borderWidth: StyleSheet.hairlineWidth,
    borderColor: colors.border,
    borderRadius: 10,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: colors.text,
    fontFamily: fonts.body,
    fontSize: 14,
  },
  multiline: { minHeight: 64, textAlignVertical: 'top' },
  meta: { color: colors.textMuted, fontSize: 13 },
  convRow: { gap: spacing.xs, paddingVertical: spacing.xs },
});

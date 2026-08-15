import { useCallback, useEffect, useState } from 'react';
import {
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import type { PublicUser } from '../../api/types';
import { EmptyState } from '../../components/EmptyState';
import { LinasLoadingIndicator } from '../../components/LinasLoadingIndicator';
import { PrimaryButton } from '../../components/PrimaryButton';
import { StatusChip } from '../../components/StatusChip';
import { TextField } from '../../components/TextField';
import { useI18n } from '../../i18n/LanguageContext';
import type { StringKey } from '../../i18n/locales/en';
import { fonts, radii, spacing, useTheme } from '../../theme';
import {
  addRequestNote,
  assignRequest,
  classifyRequestsError,
  getRequest,
  retryRequestNotify,
  runFinalAction,
} from './requestsApi';
import { RequestFinalActionModal } from './RequestFinalActionModal';
import {
  canManageRequests,
  canManualChatRequests,
  canNotifyRequests,
  canViewSensitiveRequests,
} from './requestsPermissions';
import {
  CHANNEL_LABEL_KEYS,
  FINAL_ACTION_BY_TYPE,
  STATUS_LABEL_KEYS,
  TYPE_LABEL_KEYS,
  formatWhen,
  idempotencyKey,
  type RequestDetail,
} from './requestsTypes';

type LiveChatTarget = { userId: string; conversationId: string };

type Props = {
  requestId: string;
  user: PublicUser | null;
  onBack: () => void;
  onOpenLiveChat: (target: LiveChatTarget) => void;
};

type BannerError = 'action' | 'chat';

function defaultMessage(tr: (k: StringKey) => string, type: string): string {
  if (type === 'APPOINTMENT') return tr('reqDefaultConfirmAppt');
  if (type === 'ORDER') return tr('reqDefaultMarkReady');
  return tr('reqDefaultComplete');
}

function Field({ label, value }: { label: string; value?: string | null }) {
  const { colors } = useTheme();
  if (!value) return null;
  return (
    <View style={styles.field}>
      <Text style={[styles.fieldLabel, { color: colors.textMuted }]}>{label}</Text>
      <Text style={[styles.fieldValue, { color: colors.text }]}>{value}</Text>
    </View>
  );
}

/** Never show raw PII unless requestsSensitive; otherwise restricted label only. */
function gatedSensitive(
  raw: string | null | undefined,
  present: boolean | undefined,
  allowed: boolean,
  hiddenLabel: string,
): string | null {
  if (allowed && raw) return raw;
  if (present || raw) return hiddenLabel;
  return null;
}

export function RequestDetailView({ requestId, user, onBack, onOpenLiveChat }: Props) {
  const { colors } = useTheme();
  const { tr, language } = useI18n();
  const [detail, setDetail] = useState<RequestDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [bannerError, setBannerError] = useState<BannerError | null>(null);
  const [note, setNote] = useState('');
  const [busy, setBusy] = useState(false);
  const [finalOpen, setFinalOpen] = useState(false);
  const [finalMessage, setFinalMessage] = useState('');

  const load = useCallback(async (opts?: { quiet?: boolean }) => {
    const quiet = Boolean(opts?.quiet);
    if (!quiet) setLoading(true);
    setLoadError(null);
    try {
      setDetail(await getRequest(requestId));
      setBannerError(null);
    } catch (err) {
      setLoadError(classifyRequestsError(err));
    } finally {
      if (!quiet) setLoading(false);
    }
  }, [requestId]);

  useEffect(() => {
    void load();
  }, [load]);

  if (loading && !detail) {
    return (
      <View style={styles.center}>
        <LinasLoadingIndicator variant="screen" />
      </View>
    );
  }
  if (!detail) {
    return (
      <View style={styles.centerPad}>
        <EmptyState title={tr('reqLoadError')} />
        <PrimaryButton label={tr('reqRetry')} onPress={() => void load()} />
        <PrimaryButton label={tr('reqBackToList')} onPress={onBack} variant="ghost" />
      </View>
    );
  }

  const manage = canManageRequests(user);
  const notify = canNotifyRequests(user);
  const chatOk = canManualChatRequests(user);
  const sensitiveOk = canViewSensitiveRequests(user);
  const final = FINAL_ACTION_BY_TYPE[detail.request_type];
  const typeKey = TYPE_LABEL_KEYS[detail.request_type];
  const statusKey = STATUS_LABEL_KEYS[detail.status];
  const channelKey = detail.source_channel ? CHANNEL_LABEL_KEYS[detail.source_channel] : null;

  async function withBusy(fn: () => Promise<void>) {
    setBusy(true);
    setBannerError(null);
    try {
      await fn();
    } catch {
      setBannerError('action');
    } finally {
      setBusy(false);
    }
  }

  const refresh = () => load({ quiet: true });

  return (
    <ScrollView contentContainerStyle={styles.pad}>
      <Pressable onPress={onBack} accessibilityRole="button">
        <Text style={{ color: colors.accent, fontFamily: fonts.bodyMedium }}>{tr('reqBackToList')}</Text>
      </Pressable>

      <Text style={[styles.title, { color: colors.text }]}>
        {detail.customer_display_name || detail.customer_name || detail.request_number}
      </Text>
      <View style={styles.chips}>
        {typeKey ? <StatusChip label={tr(typeKey)} /> : null}
        {statusKey ? <StatusChip label={tr(statusKey)} tone="ok" /> : null}
        {channelKey ? <StatusChip label={tr(channelKey)} /> : null}
      </View>

      <Field label={tr('reqNumber')} value={detail.request_number} />
      <Field label={tr('reqCreated')} value={formatWhen(detail.created_at, language)} />
      <Field
        label={tr('reqPreferred')}
        value={[detail.preferred_date, detail.preferred_time].filter(Boolean).join(' · ') || null}
      />
      <Field label={tr('reqBranch')} value={detail.requested_branch} />
      <Field label={tr('reqFulfillment')} value={detail.fulfillment_preference} />
      <Field
        label={tr('reqItems')}
        value={
          detail.requested_items
            ? typeof detail.requested_items === 'string'
              ? detail.requested_items
              : JSON.stringify(detail.requested_items)
            : detail.title
        }
      />
      <Field label={tr('reqCustomerNotes')} value={detail.customer_notes} />
      <Field
        label={tr('reqPhone')}
        value={gatedSensitive(
          detail.phone_normalized,
          detail.phone_present,
          sensitiveOk,
          tr('reqPresentHidden'),
        )}
      />
      <Field
        label={tr('reqEmail')}
        value={gatedSensitive(detail.email, detail.email_present, sensitiveOk, tr('reqPresentHidden'))}
      />
      <Field
        label={tr('reqAddress')}
        value={gatedSensitive(
          detail.delivery_address,
          detail.delivery_address_present,
          sensitiveOk,
          tr('reqPresentHidden'),
        )}
      />

      {loadError ? (
        <Text style={[styles.err, { color: colors.danger }]}>{tr('reqLoadError')}</Text>
      ) : null}

      {chatOk ? (
        <PrimaryButton
          label={tr('reqChatCustomer')}
          onPress={() => {
            const userId = detail.external_customer_id;
            const conversationId = detail.conversation_id;
            if (userId && conversationId) {
              onOpenLiveChat({ userId, conversationId });
            } else {
              setBannerError('chat');
            }
          }}
          style={styles.gap}
        />
      ) : null}
      {bannerError === 'chat' ? (
        <Text style={[styles.err, { color: colors.danger }]}>{tr('reqChatUnavailable')}</Text>
      ) : null}

      {manage ? (
        <View style={styles.row}>
          <PrimaryButton
            label={tr('reqAssign')}
            onPress={() =>
              void withBusy(async () => {
                if (!user?.id) return;
                await assignRequest(detail.request_id, {
                  assigned_user_id: user.id,
                  row_version: detail.row_version,
                });
                await refresh();
              })
            }
            loading={busy}
            disabled={busy}
            style={styles.half}
          />
          <PrimaryButton
            label={tr('reqUnassign')}
            variant="ghost"
            onPress={() =>
              void withBusy(async () => {
                await assignRequest(detail.request_id, {
                  assigned_user_id: null,
                  row_version: detail.row_version,
                });
                await refresh();
              })
            }
            disabled={busy}
            style={styles.half}
          />
        </View>
      ) : null}

      {notify && final ? (
        <PrimaryButton
          label={tr(final.labelKey)}
          onPress={() => {
            setFinalMessage(detail.completion_message || defaultMessage(tr, detail.request_type));
            setFinalOpen(true);
          }}
          disabled={busy}
          style={styles.gap}
        />
      ) : null}

      {notify && detail.notification_status === 'failed' ? (
        <PrimaryButton
          label={tr('reqNotifyRetry')}
          variant="ghost"
          onPress={() =>
            void withBusy(async () => {
              await retryRequestNotify(detail.request_id, idempotencyKey('notify'));
              await refresh();
            })
          }
          disabled={busy}
          style={styles.gap}
        />
      ) : null}

      {bannerError === 'action' ? (
        <Text style={[styles.err, { color: colors.danger }]}>{tr('reqActionError')}</Text>
      ) : null}

      <Text style={[styles.section, { color: colors.text }]}>{tr('reqNotes')}</Text>
      {(detail.notes || []).map((n) => (
        <View key={n.id} style={[styles.note, { borderColor: colors.border }]}>
          <Text style={{ color: colors.textDim, fontSize: 11 }}>{formatWhen(n.created_at, language)}</Text>
          <Text style={{ color: colors.text, fontFamily: fonts.body }}>{n.body}</Text>
        </View>
      ))}
      {manage ? (
        <>
          <TextField
            value={note}
            onChangeText={setNote}
            placeholder={tr('reqNotePlaceholder')}
            multiline
          />
          <PrimaryButton
            label={tr('reqSaveNote')}
            onPress={() =>
              void withBusy(async () => {
                if (!note.trim()) return;
                await addRequestNote(detail.request_id, note.trim());
                setNote('');
                await refresh();
              })
            }
            disabled={busy || !note.trim()}
          />
        </>
      ) : null}

      <Text style={[styles.section, { color: colors.text }]}>{tr('reqTimeline')}</Text>
      {(detail.events || []).map((ev) => (
        <View key={ev.id} style={styles.event}>
          <Text style={{ color: colors.textMuted, fontSize: 12 }}>
            {formatWhen(ev.created_at, language)} · {ev.event_type}
          </Text>
        </View>
      ))}

      <RequestFinalActionModal
        visible={finalOpen}
        title={final ? tr(final.labelKey) : tr('reqFinalPreviewTitle')}
        message={finalMessage}
        busy={busy}
        onChangeMessage={setFinalMessage}
        onCancel={() => setFinalOpen(false)}
        onConfirm={() =>
          void withBusy(async () => {
            if (!final) return;
            await runFinalAction(detail.request_id, {
              action: final.action,
              row_version: detail.row_version,
              completion_message: finalMessage,
              idempotency_key: idempotencyKey('final'),
              send_notification: true,
            });
            setFinalOpen(false);
            await refresh();
          })
        }
      />
    </ScrollView>
  );
}

const styles = StyleSheet.create({
  center: { flex: 1, alignItems: 'center', justifyContent: 'center' },
  centerPad: { flex: 1, justifyContent: 'center', padding: spacing.xl, gap: spacing.md },
  pad: { padding: spacing.lg, paddingBottom: spacing.xxl, gap: spacing.sm },
  title: { fontFamily: fonts.bodyMedium, fontSize: 20, marginTop: spacing.md },
  chips: { flexDirection: 'row', flexWrap: 'wrap', gap: 6, marginVertical: spacing.sm },
  field: { marginBottom: spacing.sm },
  fieldLabel: { fontFamily: fonts.body, fontSize: 12 },
  fieldValue: { fontFamily: fonts.body, fontSize: 15, marginTop: 2 },
  section: { fontFamily: fonts.bodyMedium, fontSize: 16, marginTop: spacing.lg, marginBottom: spacing.sm },
  note: { borderWidth: 1, borderRadius: radii.md, padding: spacing.md, marginBottom: spacing.sm, gap: 4 },
  event: { marginBottom: 6 },
  row: { flexDirection: 'row', gap: spacing.sm, marginTop: spacing.md },
  half: { flex: 1 },
  gap: { marginTop: spacing.md },
  err: { fontFamily: fonts.body, fontSize: 13, marginTop: 6 },
});

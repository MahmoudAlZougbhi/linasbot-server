import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { colors, fonts, radii, spacing } from '../../theme';
import type { CreativeDraft } from './useChatSession';

type Props = {
  draft: CreativeDraft;
  busy?: boolean;
  onEdit: () => void;
  onRegenerate: () => void;
  onSchedule: () => void;
  onDismiss: () => void;
};

export function CreativeDraftCard({
  draft,
  busy,
  onEdit,
  onRegenerate,
  onSchedule,
  onDismiss,
}: Props) {
  const actions = draft.actions || {};
  const status = draft.status || 'completed';
  const body =
    status === 'needs_brief'
      ? 'Pick a task chip (Auto / Compress / …) or describe the post, then send.'
      : status === 'unavailable'
        ? draft.reason || 'Not available yet.'
        : status === 'queued'
          ? `Queued ${draft.kind || ''} job${draft.job_id ? ` (${draft.job_id})` : ''}.`
          : draft.text || '';

  return (
    <View style={styles.card}>
      <View style={styles.header}>
        <Text style={styles.title}>
          {status === 'needs_brief' ? 'Create Post' : `Draft · ${draft.kind || 'post'}`}
        </Text>
        <Pressable onPress={onDismiss} hitSlop={8}>
          <Text style={styles.dismiss}>Close</Text>
        </Pressable>
      </View>
      {body ? <Text style={styles.body}>{body}</Text> : null}
      {!actions.publish ? (
        <Text style={styles.gate}>
          {actions.publish_reason || 'Publish stays gated until Meta content_publish is live_verified.'}
        </Text>
      ) : null}
      {status === 'completed' || status === 'queued' ? (
        <View style={styles.actions}>
          {actions.edit !== false ? (
            <Pressable style={styles.btn} onPress={onEdit} disabled={busy}>
              <Text style={styles.btnText}>Edit</Text>
            </Pressable>
          ) : null}
          {actions.regenerate !== false ? (
            <Pressable style={styles.btn} onPress={onRegenerate} disabled={busy}>
              {busy ? (
                <ActivityIndicator color={colors.accent} />
              ) : (
                <Text style={styles.btnText}>Regenerate</Text>
              )}
            </Pressable>
          ) : null}
          {actions.schedule !== false ? (
            <Pressable style={styles.btn} onPress={onSchedule} disabled={busy}>
              <Text style={styles.btnText}>Schedule</Text>
            </Pressable>
          ) : null}
          <Pressable style={[styles.btn, styles.btnDisabled]} disabled>
            <Text style={styles.btnMuted}>Publish</Text>
          </Pressable>
        </View>
      ) : null}
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    marginHorizontal: 16,
    marginBottom: 8,
    backgroundColor: colors.surface,
    borderRadius: radii.md,
    padding: spacing.md,
    borderColor: colors.accent,
    borderWidth: 1,
    gap: 8,
  },
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  title: { color: colors.text, fontFamily: fonts.bodyMedium, fontSize: 14 },
  dismiss: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 12 },
  body: { color: colors.text, fontFamily: fonts.body, fontSize: 13, lineHeight: 19 },
  gate: { color: colors.textMuted, fontFamily: fonts.body, fontSize: 11 },
  actions: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  btn: {
    minWidth: 88,
    backgroundColor: colors.accentSoft,
    borderRadius: 12,
    paddingVertical: 10,
    paddingHorizontal: 12,
    borderColor: colors.accent,
    borderWidth: 1,
    alignItems: 'center',
  },
  btnDisabled: { opacity: 0.45, backgroundColor: colors.bgElevated, borderColor: colors.border },
  btnText: { color: colors.accent, fontFamily: fonts.bodyMedium, fontSize: 12 },
  btnMuted: { color: colors.textMuted, fontFamily: fonts.bodyMedium, fontSize: 12 },
});

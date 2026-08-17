import { useCallback, useEffect, useState } from 'react';
import { Image, StyleSheet, Text, View } from 'react-native';
import { z } from 'zod';

import { ApiError, apiFetch } from '../../../api/client';
import { LinasLoadingIndicator } from '../../../components/LinasLoadingIndicator';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import { CommentSegmented } from './CommentSegmented';
import { CM_BORDER, CM_MUTED, CM_RADIUS, CM_TEAL_DARK } from './commentChrome';

const InboxItemSchema = z
  .object({
    comment_id: z.string().optional(),
    text: z.string().optional(),
    author_username: z.string().optional(),
    author_avatar_url: z.string().optional(),
    create_time: z.string().nullable().optional(),
    post_preview: z.string().optional(),
    post_thumbnail: z.string().optional(),
    ai_reply: z.string().optional(),
    delivery_status: z.string().optional(),
    delivery_error: z.string().optional(),
    automation: z.boolean().optional(),
  })
  .passthrough();

const InboxSchema = z
  .object({
    success: z.boolean().optional(),
    status: z.string().optional(),
    comments: z.array(InboxItemSchema).optional(),
  })
  .passthrough();

type InboxRow = z.infer<typeof InboxItemSchema>;

type Props = {
  tr: (key: StringKey) => string;
};

export function CommentInboxView({ tr }: Props) {
  const [status, setStatus] = useState('loading');
  const [items, setItems] = useState<InboxRow[]>([]);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setError(null);
    try {
      const data = await apiFetch('/api/comments/inbox?platform=tiktok', { schema: InboxSchema });
      setStatus(String(data.status || 'ok'));
      setItems(Array.isArray(data.comments) ? data.comments : []);
    } catch (err) {
      setStatus('error');
      setError(err instanceof ApiError ? tr('commentsInboxError') : tr('commentsInboxError'));
    }
  }, [tr]);

  useEffect(() => {
    void load();
  }, [load]);

  return (
    <View style={styles.wrap}>
      <CommentSegmented
        label={tr('commentsFilterTikTok')}
        value="tiktok"
        options={[{ id: 'tiktok', label: tr('commentsFilterTikTok') }]}
        onChange={() => undefined}
      />
      {status === 'loading' && items.length === 0 ? <LinasLoadingIndicator variant="inline" /> : null}
      {status === 'disconnected' ? <Text style={styles.state}>{tr('commentsInboxDisconnected')}</Text> : null}
      {status === 'permission_pending' ? (
        <Text style={styles.state}>{tr('commentsInboxPermissionPending')}</Text>
      ) : null}
      {status === 'error' || error ? <Text style={styles.error}>{error || tr('commentsInboxError')}</Text> : null}
      {status === 'empty' || (status === 'ok' && items.length === 0) ? (
        <Text style={styles.state}>{tr('commentsInboxEmpty')}</Text>
      ) : null}
      {items.map((item) => (
        <View key={item.comment_id || item.text} style={styles.card}>
          {item.post_thumbnail ? (
            <Image source={{ uri: item.post_thumbnail }} style={styles.thumb} />
          ) : null}
          <Text style={styles.preview} numberOfLines={2}>
            {item.post_preview || tr('commentsUntitledPost')}
          </Text>
          <Text style={styles.author}>{item.author_username || 'TikTok'}</Text>
          <Text style={styles.body}>{item.text}</Text>
          {item.ai_reply ? <Text style={styles.reply}>{item.ai_reply}</Text> : null}
          <Text style={styles.meta}>
            {item.create_time ? new Date(item.create_time).toLocaleString() : ''}
            {item.delivery_status === 'sent'
              ? ` · ${tr('commentsDeliverySent')}`
              : item.delivery_status === 'failed'
                ? ` · ${tr('commentsDeliveryFailed')}`
                : ` · ${tr('commentsDeliveryNone')}`}
            {` · ${item.automation ? tr('commentsAutomationOn') : tr('commentsAutomationOff')}`}
          </Text>
          {item.delivery_error ? <Text style={styles.error}>{item.delivery_error}</Text> : null}
        </View>
      ))}
    </View>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12, paddingBottom: 28 },
  state: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 14 },
  error: { color: '#DC2626', fontFamily: fonts.body, fontSize: 13 },
  card: {
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS,
    padding: 12,
    gap: 6,
    backgroundColor: '#FFFFFF',
  },
  thumb: { width: '100%', height: 140, borderRadius: 8, backgroundColor: '#F3F4F6' },
  preview: { color: CM_TEAL_DARK, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
  author: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 13 },
  body: { color: '#111827', fontFamily: fonts.body, fontSize: 15 },
  reply: { color: CM_TEAL_DARK, fontFamily: fonts.body, fontSize: 14 },
  meta: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 12 },
});

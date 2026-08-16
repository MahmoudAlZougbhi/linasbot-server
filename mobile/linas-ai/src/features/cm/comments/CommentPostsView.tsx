import { Image, Linking, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';

import { AppIcon, feather } from '../../../components/AppIcon';
import { PrimaryButton } from '../../../components/PrimaryButton';
import type { StringKey } from '../../../i18n';
import { fonts } from '../../../theme';
import type { CommentAccount, ConnectedPost } from './commentPostsApi';
import {
  CM_BORDER,
  CM_MUTED,
  CM_RADIUS,
  CM_RADIUS_SM,
  CM_TEAL,
  CM_TEAL_DARK,
  CM_TEAL_SOFT,
} from './commentChrome';
import { formatPostStamp, postTitle } from './commentModel';

type Props = {
  posts: ConnectedPost[];
  selectedIds: string[];
  query: string;
  loading: boolean;
  error: string | null;
  allowManual: boolean;
  manualId: string;
  nextAfter: string;
  accounts: CommentAccount[];
  accountId: string;
  onAccount: (id: string) => void;
  onQueryChange: (value: string) => void;
  onToggle: (id: string) => void;
  onManualId: (value: string) => void;
  onAddManual: () => void;
  onLoadMore: () => void;
  onConfirm: () => void;
  tr: (key: StringKey) => string;
};

export function CommentPostsView({
  posts,
  selectedIds,
  query,
  loading,
  error,
  allowManual,
  manualId,
  nextAfter,
  accounts,
  accountId,
  onAccount,
  onQueryChange,
  onToggle,
  onManualId,
  onAddManual,
  onLoadMore,
  onConfirm,
  tr,
}: Props) {
  const selected = new Set(selectedIds);
  const needle = query.trim().toLowerCase();
  const visible = posts.filter((post) => {
    if (!needle) return true;
    return `${post.preview} ${post.id}`.toLowerCase().includes(needle);
  });
  const count = selectedIds.length;
  const confirmLabel =
    count === 1
      ? tr('commentsUseSelectedOne')
      : tr('commentsUseSelected').replace('{count}', String(count));

  return (
    <View style={styles.wrap}>
      <Text style={styles.hero}>{tr('commentsChooseTitle')}</Text>
      <Text style={styles.subtitle}>{tr('commentsChooseSubtitle')}</Text>

      {accounts.length > 1 ? (
        <View style={styles.accountRow}>
          {accounts.map((account) => {
            const on = account.connected_account_id === accountId;
            return (
              <Pressable
                key={account.connected_account_id}
                onPress={() => onAccount(account.connected_account_id)}
                style={[styles.accountChip, on && styles.accountOn]}
              >
                <Text style={[styles.accountText, on && styles.accountTextOn]} numberOfLines={1}>
                  {account.name}
                </Text>
              </Pressable>
            );
          })}
        </View>
      ) : null}

      <View style={styles.search}>
        <AppIcon icon={feather('search')} size={18} color={CM_MUTED} />
        <TextInput
          value={query}
          onChangeText={onQueryChange}
          placeholder={tr('commentsSearchPosts')}
          placeholderTextColor={CM_MUTED}
          style={styles.searchInput}
          autoCapitalize="none"
          autoCorrect={false}
        />
      </View>

      <Text style={styles.section}>{tr('commentsPostsHeader')}</Text>
      {error ? <Text style={styles.error}>{error}</Text> : null}
      {loading && !posts.length ? <Text style={styles.empty}>{tr('commentsPostsLoading')}</Text> : null}
      {!loading && !visible.length && !error ? <Text style={styles.empty}>{tr('commentsNoPosts')}</Text> : null}

      {visible.map((post) => (
        <PostCard
          key={post.id}
          post={post}
          selected={selected.has(post.id)}
          platform={accounts.find((row) => row.connected_account_id === accountId)?.platform || 'instagram'}
          untitled={tr('commentsUntitledPost')}
          previewLabel={tr('commentsPreviewPost')}
          onToggle={() => onToggle(post.id)}
        />
      ))}

      {selectedIds
        .filter((id) => !posts.some((post) => post.id === id))
        .map((id) => (
          <PostCard
            key={`keep-${id}`}
            post={{ id, preview: id, created_time: '', permalink: '', thumbnail: '', media_type: '' }}
            selected
            platform=""
            untitled={tr('commentsUntitledPost')}
            previewLabel={tr('commentsPreviewPost')}
            onToggle={() => onToggle(id)}
            keepLabel={tr('commentsKeptPostId')}
          />
        ))}

      {nextAfter ? (
        <Pressable onPress={onLoadMore} style={styles.moreBtn}>
          <Text style={styles.moreText}>{tr('commentsLoadMore')}</Text>
        </Pressable>
      ) : null}

      {allowManual ? (
        <View style={styles.manual}>
          <Text style={styles.label}>{tr('commentsManualPostId')}</Text>
          <Text style={styles.hint}>{tr('commentsManualPostHint')}</Text>
          <View style={styles.manualRow}>
            <TextInput
              value={manualId}
              onChangeText={onManualId}
              style={styles.manualInput}
              placeholder={tr('commentsManualPostId')}
              placeholderTextColor={CM_MUTED}
              autoCapitalize="none"
            />
            <Pressable onPress={onAddManual} style={styles.addManual}>
              <Text style={styles.addManualText}>{tr('commentsAddPostId')}</Text>
            </Pressable>
          </View>
        </View>
      ) : null}

      <PrimaryButton label={confirmLabel} onPress={onConfirm} disabled={count < 1} style={styles.confirm} />
    </View>
  );
}

function PostCard({
  post,
  selected,
  platform,
  untitled,
  previewLabel,
  onToggle,
  keepLabel,
}: {
  post: ConnectedPost;
  selected: boolean;
  platform: string;
  untitled: string;
  previewLabel: string;
  onToggle: () => void;
  keepLabel?: string;
}) {
  const stamp = formatPostStamp(post.created_time);
  const channel = platform ? platform.charAt(0).toUpperCase() + platform.slice(1) : '';
  const meta = [channel, stamp].filter(Boolean).join(' · ');
  return (
    <Pressable
      onPress={onToggle}
      accessibilityRole="button"
      accessibilityState={{ selected }}
      style={[styles.card, selected && styles.cardOn]}
    >
      {post.thumbnail ? (
        <Image source={{ uri: post.thumbnail }} style={styles.thumb} />
      ) : (
        <View style={styles.thumbFallback}>
          <AppIcon icon={feather('image')} size={18} color={CM_TEAL} />
        </View>
      )}
      <View style={styles.copy}>
        <Text style={styles.postTitle} numberOfLines={1}>
          {keepLabel ? `${keepLabel} ${post.id}` : postTitle(post.preview, untitled)}
        </Text>
        {meta ? (
          <Text style={styles.meta} numberOfLines={1}>
            {meta}
          </Text>
        ) : null}
        {post.permalink ? (
          <Pressable onPress={() => void Linking.openURL(post.permalink)}>
            <Text style={styles.preview}>{previewLabel}</Text>
          </Pressable>
        ) : null}
      </View>
      <View style={[styles.check, selected && styles.checkOn]}>
        {selected ? <AppIcon icon={feather('check')} size={14} color="#FFFFFF" /> : null}
      </View>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  wrap: { gap: 12, paddingBottom: 28 },
  hero: {
    color: CM_TEAL_DARK,
    fontFamily: fonts.bodyMedium,
    fontSize: 28,
    fontWeight: '700',
  },
  subtitle: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 15, marginTop: -6 },
  accountRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  accountChip: {
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 8,
    backgroundColor: '#FFFFFF',
  },
  accountOn: { borderColor: CM_TEAL, backgroundColor: CM_TEAL_SOFT },
  accountText: { color: CM_MUTED, fontFamily: fonts.bodyMedium, fontSize: 13 },
  accountTextOn: { color: CM_TEAL, fontWeight: '700' },
  search: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 10,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  searchInput: { flex: 1, color: CM_TEAL_DARK, fontFamily: fonts.body, fontSize: 15, padding: 0 },
  section: {
    color: CM_MUTED,
    fontFamily: fonts.bodyMedium,
    fontSize: 12,
    fontWeight: '700',
    letterSpacing: 0.6,
  },
  error: { color: '#DC2626', fontFamily: fonts.body, fontSize: 13, lineHeight: 18 },
  empty: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 14 },
  card: {
    flexDirection: 'row',
    alignItems: 'center',
    gap: 12,
    backgroundColor: '#FFFFFF',
    borderWidth: 1.5,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS,
    padding: 12,
  },
  cardOn: { borderColor: CM_TEAL },
  thumb: { width: 48, height: 48, borderRadius: CM_RADIUS_SM, backgroundColor: CM_TEAL_SOFT },
  thumbFallback: {
    width: 48,
    height: 48,
    borderRadius: CM_RADIUS_SM,
    backgroundColor: CM_TEAL_SOFT,
    alignItems: 'center',
    justifyContent: 'center',
  },
  copy: { flex: 1, gap: 2 },
  postTitle: { color: CM_TEAL_DARK, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  meta: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 12 },
  preview: { color: CM_TEAL, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '600' },
  check: {
    width: 24,
    height: 24,
    borderRadius: 12,
    borderWidth: 1.5,
    borderColor: CM_BORDER,
    alignItems: 'center',
    justifyContent: 'center',
  },
  checkOn: { backgroundColor: CM_TEAL, borderColor: CM_TEAL },
  moreBtn: { alignItems: 'center', paddingVertical: 8 },
  moreText: { color: CM_TEAL, fontFamily: fonts.bodyMedium, fontSize: 15, fontWeight: '700' },
  manual: { gap: 6 },
  label: { color: CM_TEAL_DARK, fontFamily: fonts.bodyMedium, fontSize: 14, fontWeight: '700' },
  hint: { color: CM_MUTED, fontFamily: fonts.body, fontSize: 12, lineHeight: 16 },
  manualRow: { flexDirection: 'row', gap: 8, alignItems: 'center' },
  manualInput: {
    flex: 1,
    backgroundColor: '#FFFFFF',
    borderWidth: 1,
    borderColor: CM_BORDER,
    borderRadius: CM_RADIUS_SM,
    paddingHorizontal: 12,
    paddingVertical: 10,
    color: CM_TEAL_DARK,
    fontFamily: fonts.body,
    fontSize: 14,
  },
  addManual: {
    borderWidth: 1.5,
    borderColor: CM_TEAL,
    borderRadius: CM_RADIUS_SM,
    paddingHorizontal: 12,
    paddingVertical: 10,
  },
  addManualText: { color: CM_TEAL, fontFamily: fonts.bodyMedium, fontSize: 13, fontWeight: '700' },
  confirm: { backgroundColor: CM_TEAL, borderRadius: CM_RADIUS, marginTop: 8 },
});

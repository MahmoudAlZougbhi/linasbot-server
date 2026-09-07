import { z } from 'zod';

import { apiFetch } from '../../../api/client';
import type { CommentMediaItem, CommentPlatform, CommentThreadItem, CommentWatch } from './commentsInboxTypes';

const WatchSchema = z
  .object({
    mode: z.enum(['all', 'selected']).optional(),
    post_ids: z.array(z.string()).optional(),
  })
  .passthrough();

const MediaRow = z
  .object({
    id: z.string().optional(),
    caption: z.string().optional(),
    created_time: z.string().optional(),
    permalink: z.string().optional(),
    thumbnail: z.string().optional(),
    media_type: z.string().optional(),
    kind: z.string().optional(),
    comment_count: z.number().optional(),
    watched: z.boolean().optional(),
  })
  .passthrough();

const MediaSchema = z
  .object({
    success: z.boolean().optional(),
    ok: z.boolean().optional(),
    status: z.string().optional(),
    error: z.string().optional(),
    platform: z.string().optional(),
    account_name: z.string().optional(),
    posts: z.array(MediaRow).optional(),
    next_after: z.string().optional(),
    watch: WatchSchema.optional(),
  })
  .passthrough();

const ThreadRow = z
  .object({
    comment_id: z.string().optional(),
    author: z.string().optional(),
    comment: z.string().optional(),
    ai_reply: z.string().optional(),
    created_at: z.string().optional(),
    delivery_status: z.string().optional(),
  })
  .passthrough();

const ThreadsSchema = z
  .object({
    success: z.boolean().optional(),
    status: z.string().optional(),
    threads: z.array(ThreadRow).optional(),
  })
  .passthrough();

function asWatch(raw: z.infer<typeof WatchSchema> | undefined): CommentWatch {
  return {
    mode: raw?.mode === 'selected' ? 'selected' : 'all',
    post_ids: Array.isArray(raw?.post_ids) ? raw.post_ids.map(String) : [],
  };
}

function asKind(value: string | undefined): CommentMediaItem['kind'] {
  if (value === 'reel' || value === 'video' || value === 'post') return value;
  return 'post';
}

export async function fetchCommentMedia(input: {
  platform: CommentPlatform;
  after?: string;
}): Promise<{
  status: string;
  error: string;
  accountName: string;
  posts: CommentMediaItem[];
  nextAfter: string;
  watch: CommentWatch;
}> {
  const params = new URLSearchParams({ platform: input.platform, limit: '24' });
  if (input.after) params.set('after', input.after);
  const data = await apiFetch(`/api/comments/media?${params.toString()}`, { schema: MediaSchema });
  const posts = (data.posts || [])
    .map((row) => ({
      id: String(row.id || '').trim(),
      caption: String(row.caption || ''),
      created_time: String(row.created_time || ''),
      permalink: String(row.permalink || ''),
      thumbnail: String(row.thumbnail || ''),
      media_type: String(row.media_type || ''),
      kind: asKind(row.kind),
      comment_count: Number(row.comment_count || 0),
      watched: row.watched !== false,
    }))
    .filter((row) => row.id);
  return {
    status: String(data.status || (data.ok === false ? 'error' : 'ok')),
    error: String(data.error || ''),
    accountName: String(data.account_name || ''),
    posts,
    nextAfter: String(data.next_after || ''),
    watch: asWatch(data.watch),
  };
}

export async function patchCommentWatch(input: {
  platform: CommentPlatform;
  mode?: 'all' | 'selected';
  postId?: string;
  selected?: boolean;
  knownIds?: string[];
}): Promise<CommentWatch> {
  const data = await apiFetch('/api/comments/watchlist', {
    method: 'PATCH',
    schema: z.object({ watch: WatchSchema.optional() }).passthrough(),
    body: JSON.stringify({
      platform: input.platform,
      mode: input.mode,
      post_id: input.postId,
      selected: input.selected,
      known_ids: input.knownIds,
    }),
  });
  return asWatch(data.watch);
}

export async function fetchCommentThreads(input: {
  platform: CommentPlatform;
  postId: string;
}): Promise<CommentThreadItem[]> {
  const params = new URLSearchParams({ platform: input.platform, limit: '50' });
  const data = await apiFetch(`/api/comments/media/${encodeURIComponent(input.postId)}/threads?${params}`, {
    schema: ThreadsSchema,
  });
  return (data.threads || [])
    .map((row) => ({
      comment_id: String(row.comment_id || ''),
      author: String(row.author || ''),
      comment: String(row.comment || ''),
      ai_reply: String(row.ai_reply || ''),
      created_at: String(row.created_at || ''),
      delivery_status: String(row.delivery_status || ''),
    }))
    .filter((row) => row.comment_id || row.comment);
}

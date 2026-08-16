import { z } from 'zod';

import { apiFetch } from '../../../api/client';

const AccountRow = z.object({
  platform: z.string().optional(),
  connected_account_id: z.string().optional(),
  page_or_ig_account_id: z.string().optional(),
  name: z.string().optional(),
}).passthrough();

const AccountsSchema = z
  .object({
    success: z.boolean(),
    accounts: z.array(AccountRow).optional(),
  })
  .passthrough();

const PostRow = z.object({
  id: z.string().optional(),
  preview: z.string().optional(),
  created_time: z.string().optional(),
  permalink: z.string().optional(),
  thumbnail: z.string().optional(),
  media_type: z.string().optional(),
}).passthrough();

const PostsSchema = z
  .object({
    success: z.boolean().optional(),
    ok: z.boolean().optional(),
    error: z.string().optional(),
    posts: z.array(PostRow).optional(),
    next_after: z.string().optional(),
    allow_manual_post_id: z.boolean().optional(),
  })
  .passthrough();

export type CommentAccount = {
  platform: string;
  connected_account_id: string;
  page_or_ig_account_id: string;
  name: string;
};

export type ConnectedPost = {
  id: string;
  preview: string;
  created_time: string;
  permalink: string;
  thumbnail: string;
  media_type: string;
};

export async function fetchCommentAccounts(): Promise<CommentAccount[]> {
  const data = await apiFetch('/api/cm/comment-rules/accounts', { schema: AccountsSchema });
  return (data.accounts || []).map((row) => ({
    platform: String(row.platform || ''),
    connected_account_id: String(row.connected_account_id || ''),
    page_or_ig_account_id: String(row.page_or_ig_account_id || ''),
    name: String(row.name || row.connected_account_id || ''),
  }));
}

export async function fetchConnectedPosts(input: {
  platform: string;
  connectedAccountId: string;
  after?: string;
}): Promise<{ posts: ConnectedPost[]; nextAfter: string; ok: boolean; error: string; allowManual: boolean }> {
  const params = new URLSearchParams({
    platform: input.platform,
    connected_account_id: input.connectedAccountId,
    limit: '25',
  });
  if (input.after) params.set('after', input.after);
  const data = await apiFetch(`/api/cm/comment-rules/posts?${params.toString()}`, { schema: PostsSchema });
  const posts = (data.posts || [])
    .map((row) => ({
      id: String(row.id || '').trim(),
      preview: String(row.preview || ''),
      created_time: String(row.created_time || ''),
      permalink: String(row.permalink || ''),
      thumbnail: String(row.thumbnail || ''),
      media_type: String(row.media_type || ''),
    }))
    .filter((row) => row.id);
  return {
    posts,
    nextAfter: String(data.next_after || ''),
    ok: data.ok !== false && data.success !== false,
    error: String(data.error || ''),
    allowManual: data.allow_manual_post_id !== false,
  };
}

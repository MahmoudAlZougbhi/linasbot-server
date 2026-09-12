import type { CommentMediaItem, CommentPlatform, CommentThreadItem } from './commentsInboxTypes';

function textOf(data: Record<string, unknown>, ...keys: string[]): string {
  for (const key of keys) {
    const value = data[key];
    if (value == null || typeof value === 'object') continue;
    const text = String(value).trim();
    if (text) return text;
  }
  return '';
}

export function commentEventPlatform(data: Record<string, unknown>): CommentPlatform | null {
  const raw = textOf(data, 'platform', 'channel').toLowerCase();
  if (raw === 'instagram' || raw === 'facebook' || raw === 'tiktok') return raw;
  return null;
}

export function applyCommentGridEvent(
  posts: CommentMediaItem[],
  data: Record<string, unknown>,
  platform: CommentPlatform,
): CommentMediaItem[] {
  if (commentEventPlatform(data) !== platform) return posts;
  const postId = textOf(data, 'post_id');
  if (!postId) return posts;
  return posts.map((post) =>
    post.id === postId ? { ...post, comment_count: Math.max(0, post.comment_count) + (textOf(data, 'ai_reply') ? 0 : 1) } : post,
  );
}

export function applyCommentThreadEvent(
  items: CommentThreadItem[],
  data: Record<string, unknown>,
  postId: string,
  platform: CommentPlatform,
): CommentThreadItem[] {
  if (commentEventPlatform(data) !== platform) return items;
  const eventPost = textOf(data, 'post_id');
  if (eventPost && eventPost !== postId) return items;
  const commentId = textOf(data, 'comment_id');
  if (!commentId) return items;
  const comment = textOf(data, 'comment');
  const author = textOf(data, 'author');
  const aiReply = textOf(data, 'ai_reply');
  const createdAt = textOf(data, 'created_at') || new Date().toISOString();
  const delivery = textOf(data, 'delivery_status');
  const index = items.findIndex((row) => row.comment_id === commentId);
  if (index < 0) {
    if (!comment && !aiReply) return items;
    return [
      ...items,
      {
        comment_id: commentId,
        author,
        comment,
        ai_reply: aiReply,
        created_at: createdAt,
        delivery_status: delivery || (aiReply ? 'sent' : 'none'),
      },
    ];
  }
  return items.map((row, i) => {
    if (i !== index) return row;
    return {
      ...row,
      author: author || row.author,
      comment: comment || row.comment,
      ai_reply: aiReply || row.ai_reply,
      delivery_status: delivery || (aiReply ? 'sent' : row.delivery_status),
    };
  });
}

/** Selected-post snapshots for comment rules (no React Native). */

export type SelectedCommentPost = {
  id: string;
  platform: string;
  thumbnail: string;
  caption: string;
  permalink: string;
  kind: string;
};

export function parseSelectedPost(row: unknown): SelectedCommentPost | null {
  if (!row || typeof row !== 'object') return null;
  const rec = row as Record<string, unknown>;
  const id = String(rec.id || '').trim();
  if (!id) return null;
  return {
    id,
    platform: String(rec.platform || '').trim(),
    thumbnail: String(rec.thumbnail || '').trim(),
    caption: String(rec.caption || rec.preview || '').trim(),
    permalink: String(rec.permalink || '').trim(),
    kind: String(rec.kind || 'post').trim() || 'post',
  };
}

export function parseSelectedPosts(
  row: Record<string, unknown>,
  fallbackIds: string[],
  fallbackPlatform: string,
  fallbackCaption: string,
  fallbackPermalink: string,
): SelectedCommentPost[] {
  const raw = Array.isArray(row.selected_posts) ? row.selected_posts : [];
  const parsed = raw.map(parseSelectedPost).filter((item): item is SelectedCommentPost => Boolean(item));
  if (parsed.length) return parsed;
  return fallbackIds.map((id, index) => ({
    id,
    platform: fallbackPlatform,
    thumbnail: '',
    caption: index === 0 ? fallbackCaption : '',
    permalink: index === 0 ? fallbackPermalink : '',
    kind: 'post',
  }));
}

export function applySelectedPosts<
  T extends {
    post_id: string;
    post_ids: string[];
    selected_posts: SelectedCommentPost[];
    scope: 'all_posts' | 'specific_post';
    platform: string;
    channel: string;
    post_permalink: string;
    post_caption_snapshot: string;
  },
>(item: T, posts: SelectedCommentPost[]): T {
  const seen = new Set<string>();
  const unique: SelectedCommentPost[] = [];
  for (const post of posts) {
    const id = post.id.trim();
    const platform = post.platform.trim();
    const key = `${platform}:${id}`;
    if (!id || seen.has(key)) continue;
    seen.add(key);
    unique.push({ ...post, id, platform });
  }
  const ids: string[] = [];
  for (const post of unique) {
    if (!ids.includes(post.id)) ids.push(post.id);
  }
  const platforms = [...new Set(unique.map((post) => post.platform).filter(Boolean))];
  const one = platforms.length === 1 ? platforms[0] : '';
  const channel = one === 'instagram' || one === 'facebook' || one === 'tiktok' ? one : 'any';
  return {
    ...item,
    scope: ids.length ? 'specific_post' : 'all_posts',
    post_id: ids[0] || '',
    post_ids: ids,
    selected_posts: unique,
    platform: one || item.platform,
    channel,
    post_permalink: unique[0]?.permalink || '',
    post_caption_snapshot: unique[0]?.caption || '',
  };
}

export function selectedPostsOf(item: {
  selected_posts: SelectedCommentPost[];
  post_id: string;
  post_ids: string[];
  platform: string;
  channel: string;
  post_caption_snapshot: string;
  post_permalink: string;
}): SelectedCommentPost[] {
  if (item.selected_posts.length) return item.selected_posts;
  return parseSelectedPosts(
    {},
    item.post_ids.length ? item.post_ids : item.post_id ? [item.post_id] : [],
    item.platform || item.channel,
    item.post_caption_snapshot,
    item.post_permalink,
  );
}

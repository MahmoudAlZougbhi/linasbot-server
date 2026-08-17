/** Pure Comment Rule helpers (no React Native). */

export type CommentKind = 'image' | 'video' | 'file' | 'link';
export type CommentReplyType = 'automatic' | 'ai';
export type CommentPostsMode = 'all' | 'choose';
export type CommentReplyIn = 'comment' | 'dm' | 'both';

export type CommentAttachment = {
  id: string;
  kind: CommentKind;
  title: string;
  description: string;
  caption: string;
  mime: string;
  filename: string;
  size: number;
  url: string;
  duration_seconds: number | null;
};

export type CommentRuleItem = {
  id: string;
  enabled: boolean;
  name: string;
  scope: 'all_posts' | 'specific_post';
  rule_mode: 'deterministic' | 'ai_guidance';
  trigger_type: string;
  priority: number;
  revision: number;
  match_mode: string;
  keywords: string[];
  pattern: string;
  post_id: string;
  post_ids: string[];
  platform: string;
  connected_account_id: string;
  page_or_ig_account_id: string;
  post_permalink: string;
  post_caption_snapshot: string;
  post_status: string;
  channel: string;
  action: string;
  reply_template: string;
  dm_template: string;
  ai_instructions: string;
  notes: string | null;
  attachments: CommentAttachment[];
};

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function asStringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  const out: string[] = [];
  for (const raw of value) {
    const text = String(raw || '').trim();
    if (text && !out.includes(text)) out.push(text);
  }
  return out;
}

function parseResourceFields(row: Record<string, unknown>): { title: string; description: string } {
  return {
    title: String(row.title || '').trim(),
    description: String(row.description || row.caption || '').trim(),
  };
}

function serializeResourceFields(fields: { title: string; description: string }): {
  title: string;
  description: string;
  caption: string;
} {
  const title = fields.title.trim();
  const description = fields.description.trim();
  return { title, description, caption: description };
}

export function parseAttachment(row: Record<string, unknown>): CommentAttachment {
  const durationRaw = row.duration_seconds;
  const duration =
    typeof durationRaw === 'number' && Number.isFinite(durationRaw) && durationRaw >= 0
      ? Math.round(durationRaw)
      : null;
  const mime = String(row.mime || '').toLowerCase();
  let kind: CommentKind = 'file';
  if (row.kind === 'link' || String(row.url || '').trim()) kind = 'link';
  else if (row.kind === 'video' || mime.startsWith('video/')) kind = 'video';
  else if (row.kind === 'image' || mime.startsWith('image/')) kind = 'image';
  else if (row.kind === 'file') kind = 'file';
  const meta = parseResourceFields(row);
  return {
    id: String(row.id || ''),
    kind,
    title: meta.title,
    description: meta.description,
    caption: meta.description,
    mime: String(row.mime || ''),
    filename: String(row.filename || ''),
    size: typeof row.size === 'number' && Number.isFinite(row.size) ? row.size : 0,
    url: String(row.url || ''),
    duration_seconds: duration,
  };
}

export function uniquePostIds(rule: Pick<CommentRuleItem, 'post_id' | 'post_ids'>): string[] {
  return asStringList([...(rule.post_ids || []), rule.post_id]);
}

export function parseCommentRule(row: Record<string, unknown>): CommentRuleItem {
  const atts = Array.isArray(row.attachments) ? row.attachments : [];
  const postIds = uniquePostIds({
    post_id: String(row.post_id || ''),
    post_ids: asStringList(row.post_ids),
  });
  const scope = postIds.length ? 'specific_post' : row.scope === 'specific_post' ? 'specific_post' : 'all_posts';
  return {
    id: String(row.id || ''),
    enabled: row.enabled !== false,
    name: String(row.name || ''),
    scope,
    rule_mode: row.rule_mode === 'ai_guidance' ? 'ai_guidance' : 'deterministic',
    trigger_type: String(row.trigger_type || 'contains_any'),
    priority: typeof row.priority === 'number' ? row.priority : Number(row.priority) || 0,
    revision: typeof row.revision === 'number' ? row.revision : Number(row.revision) || 1,
    match_mode: String(row.match_mode || 'any_keyword'),
    keywords: asStringList(row.keywords),
    pattern: String(row.pattern || ''),
    post_id: postIds[0] || '',
    post_ids: postIds,
    platform: String(row.platform || ''),
    connected_account_id: String(row.connected_account_id || ''),
    page_or_ig_account_id: String(row.page_or_ig_account_id || ''),
    post_permalink: String(row.post_permalink || ''),
    post_caption_snapshot: String(row.post_caption_snapshot || ''),
    post_status: String(row.post_status || ''),
    channel: String(row.channel || 'any'),
    action: String(
      row.rule_mode === 'ai_guidance'
        ? row.ai_action_mode || row.action || 'reply_comment'
        : row.static_action || row.action || 'reply_comment_and_dm_static',
    ),
    reply_template: String(row.reply_template || ''),
    dm_template: String(row.dm_template || ''),
    ai_instructions: String(row.ai_instructions || row.notes || ''),
    notes: row.notes == null ? null : String(row.notes),
    attachments: atts
      .filter((item): item is Record<string, unknown> => Boolean(item) && typeof item === 'object')
      .map(parseAttachment),
  };
}

export function ruleToRecord(item: CommentRuleItem): Record<string, unknown> {
  const postIds = uniquePostIds(item);
  const replyIn = replyInOf(item);
  const isAi = item.rule_mode === 'ai_guidance';
  return {
    id: item.id,
    enabled: item.enabled,
    name: item.name,
    scope: postIds.length ? 'specific_post' : 'all_posts',
    rule_mode: item.rule_mode,
    trigger_type: isAi ? 'all_comments' : item.trigger_type || 'contains_any',
    priority: item.priority,
    revision: item.revision,
    match_mode: item.match_mode || 'any_keyword',
    keywords: isAi ? [] : item.keywords,
    pattern: item.pattern,
    post_id: postIds[0] || '',
    post_ids: postIds,
    platform: item.platform,
    connected_account_id: item.connected_account_id,
    page_or_ig_account_id: item.page_or_ig_account_id,
    post_permalink: item.post_permalink,
    post_caption_snapshot: item.post_caption_snapshot,
    post_status: item.post_status,
    channel: item.channel || 'any',
    action: isAi ? aiActionOf(replyIn) : staticActionOf(replyIn),
    reply_template: isAi ? '' : item.reply_template,
    dm_template: isAi ? '' : item.dm_template || item.reply_template,
    ai_instructions: isAi ? item.ai_instructions : '',
    ai_action_mode: isAi ? aiActionOf(replyIn) : 'reply_comment',
    notes: item.notes,
    attachments: filterAttachmentsForReplyIn(item.attachments, replyIn).map((att) => {
      const meta = serializeResourceFields({ title: att.title, description: att.description || att.caption });
      return {
        id: att.id,
        kind: att.kind,
        title: meta.title,
        description: meta.description,
        caption: meta.caption,
        mime: att.mime,
        filename: att.filename,
        size: att.size,
        url: att.url,
        duration_seconds: att.duration_seconds,
        status: 'active',
      };
    }),
  };
}

export function createCommentRule(id: string): CommentRuleItem {
  return {
    id,
    enabled: true,
    name: '',
    scope: 'all_posts',
    rule_mode: 'deterministic',
    trigger_type: 'contains_any',
    priority: 10,
    revision: 1,
    match_mode: 'any_keyword',
    keywords: [],
    pattern: '',
    post_id: '',
    post_ids: [],
    platform: 'instagram',
    connected_account_id: '',
    page_or_ig_account_id: '',
    post_permalink: '',
    post_caption_snapshot: '',
    post_status: '',
    channel: 'any',
    action: 'reply_comment_and_dm_static',
    reply_template: '',
    dm_template: '',
    ai_instructions: '',
    notes: null,
    attachments: [],
  };
}

export function matchesCommentQuery(item: CommentRuleItem, query: string): boolean {
  const needle = query.trim().toLowerCase();
  if (!needle) return true;
  const hay = [item.name, item.ai_instructions, item.reply_template, item.keywords.join(' ')].join(' ').toLowerCase();
  return hay.includes(needle);
}

export function replyTypeOf(item: CommentRuleItem): CommentReplyType {
  return item.rule_mode === 'ai_guidance' ? 'ai' : 'automatic';
}

export function postsModeOf(item: CommentRuleItem): CommentPostsMode {
  return uniquePostIds(item).length || item.scope === 'specific_post' ? 'choose' : 'all';
}

export function replyInOf(item: CommentRuleItem): CommentReplyIn {
  const raw = String(item.action || '').toLowerCase();
  // Legacy "ignore" is not selectable in owner UI; show as Comment.
  if (raw === 'ignore') return 'comment';
  if (raw.includes('comment') && raw.includes('dm')) return 'both';
  if (raw.includes('dm')) return 'dm';
  return 'comment';
}

export function staticActionOf(replyIn: CommentReplyIn): string {
  if (replyIn === 'dm') return 'send_dm_static';
  if (replyIn === 'both') return 'reply_comment_and_dm_static';
  return 'reply_comment_static';
}

export function aiActionOf(replyIn: CommentReplyIn): string {
  if (replyIn === 'dm') return 'send_dm';
  if (replyIn === 'both') return 'reply_comment_and_dm';
  return 'reply_comment';
}

export function includesDm(replyIn: CommentReplyIn): boolean {
  return replyIn === 'dm' || replyIn === 'both';
}

export function allowedResourceKinds(replyIn: CommentReplyIn): CommentKind[] {
  return includesDm(replyIn) ? ['image', 'video', 'file', 'link'] : ['image', 'link'];
}

export function filterAttachmentsForReplyIn(
  attachments: CommentAttachment[],
  replyIn: CommentReplyIn,
): CommentAttachment[] {
  const allowed = new Set(allowedResourceKinds(replyIn));
  return attachments.filter((att) => allowed.has(att.kind));
}

export function applyReplyType(item: CommentRuleItem, type: CommentReplyType): CommentRuleItem {
  if (type === 'ai') {
    return { ...item, rule_mode: 'ai_guidance', trigger_type: 'all_comments', action: aiActionOf(replyInOf(item)) };
  }
  return {
    ...item,
    rule_mode: 'deterministic',
    trigger_type: 'contains_any',
    action: staticActionOf(replyInOf(item)),
  };
}

export function applyReplyIn(item: CommentRuleItem, replyIn: CommentReplyIn): CommentRuleItem {
  const isAi = item.rule_mode === 'ai_guidance';
  const action = isAi ? aiActionOf(replyIn) : staticActionOf(replyIn);
  const message = item.reply_template;
  return {
    ...item,
    action,
    reply_template: isAi ? '' : message,
    dm_template: isAi || replyIn === 'comment' ? '' : message,
    attachments: filterAttachmentsForReplyIn(item.attachments, replyIn),
  };
}

export function applyPostsMode(item: CommentRuleItem, mode: CommentPostsMode): CommentRuleItem {
  if (mode === 'all') {
    return {
      ...item,
      scope: 'all_posts',
      post_id: '',
      post_ids: [],
      post_permalink: '',
      post_caption_snapshot: '',
    };
  }
  return { ...item, scope: 'specific_post' };
}

export function applySelectedPosts(
  item: CommentRuleItem,
  postIds: string[],
  snapshot?: { permalink?: string; caption?: string; platform?: string; accountId?: string; pageId?: string },
): CommentRuleItem {
  const ids = asStringList(postIds);
  return {
    ...item,
    scope: ids.length ? 'specific_post' : 'all_posts',
    post_id: ids[0] || '',
    post_ids: ids,
    post_permalink: snapshot?.permalink ?? item.post_permalink,
    post_caption_snapshot: snapshot?.caption ?? item.post_caption_snapshot,
    platform: snapshot?.platform ?? item.platform,
    connected_account_id: snapshot?.accountId ?? item.connected_account_id,
    page_or_ig_account_id: snapshot?.pageId ?? item.page_or_ig_account_id,
    channel: snapshot?.platform || item.channel,
  };
}

export function parseKeywords(value: string): string[] {
  return value
    .split(',')
    .map((part) => part.trim())
    .filter(Boolean);
}

export function formatDuration(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  const m = Math.floor(total / 60);
  const s = total % 60;
  return `${m}:${String(s).padStart(2, '0')}`;
}

export function formatPostStamp(iso: string, now = new Date()): string {
  const parsed = Date.parse(iso);
  if (!Number.isFinite(parsed)) return '';
  const date = new Date(parsed);
  return `${MONTHS[date.getMonth()]} ${date.getDate()}, ${date.getFullYear() || now.getFullYear()}`;
}

export function postTitle(preview: string, fallback: string): string {
  const line = preview.trim().split('\n')[0]?.trim() || '';
  return line || fallback;
}

export function isValidHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value.trim());
    return parsed.protocol === 'http:' || parsed.protocol === 'https:';
  } catch {
    return false;
  }
}

export function replyInLabelKey(replyIn: CommentReplyIn): 'commentsReplyComment' | 'commentsReplyDm' | 'commentsReplyBoth' {
  if (replyIn === 'dm') return 'commentsReplyDm';
  if (replyIn === 'both') return 'commentsReplyBoth';
  return 'commentsReplyComment';
}

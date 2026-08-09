export type CreatePostTaskId =
  | 'auto'
  | 'compress'
  | 'caption'
  | 'post'
  | 'rewrite'
  | 'campaign_ideas'
  | 'image'
  | 'video';

export type CreatePostTask = {
  id: CreatePostTaskId;
  label: string;
  disabled?: boolean;
};

/** Chat task chips aligned with Creative Studio kinds + Auto/Compress. */
export const CREATE_POST_TASKS: CreatePostTask[] = [
  { id: 'auto', label: 'Auto' },
  { id: 'compress', label: 'Compress' },
  { id: 'caption', label: 'Caption' },
  { id: 'post', label: 'Post' },
  { id: 'rewrite', label: 'Rewrite' },
  { id: 'campaign_ideas', label: 'Campaign' },
  { id: 'image', label: 'Image' },
  { id: 'video', label: 'Video', disabled: true },
];

export function looksLikeCreatePostIntent(text: string): boolean {
  const t = text.trim().toLowerCase();
  if (!t) return false;
  return (
    /create(\s+a)?\s+post|make(\s+a)?\s+post|draft(\s+a)?\s+(post|caption)/i.test(t) ||
    /بدي\s*(نعمل|اعمل|أعمل)\s*(بوست|منشور)/i.test(t) ||
    /أريد\s*(أن\s*)?(أعمل|انشئ|أنشئ)\s*(بوست|منشور)/i.test(t) ||
    /انشاء\s*منشور|اعمل\s*(بوست|منشور)/i.test(t) ||
    /créer(\s+une)?\s+(publication|post)/i.test(t)
  );
}

export type CommentPlatform = 'instagram' | 'facebook' | 'tiktok';
export type CommentMediaKind = 'post' | 'reel' | 'video';

export type CommentWatch = {
  mode: 'all' | 'selected';
  post_ids: string[];
};

export type CommentMediaItem = {
  id: string;
  caption: string;
  created_time: string;
  permalink: string;
  thumbnail: string;
  media_type: string;
  kind: CommentMediaKind;
  comment_count: number;
  watched: boolean;
};

export type CommentThreadItem = {
  comment_id: string;
  author: string;
  comment: string;
  ai_reply: string;
  created_at: string;
  delivery_status: string;
};

/** Product link kinds + display helpers for AI Setup Products. */

import type { Product } from './productsApi';

export type ChannelPlatform = 'instagram' | 'facebook' | 'tiktok' | 'youtube';

export const CHANNEL_PLATFORMS: ChannelPlatform[] = [
  'instagram',
  'facebook',
  'tiktok',
  'youtube',
];

export const CHANNEL_PREFIX = 'channel:';
export const ASSET_VIDEO = 'asset:video';
export const ASSET_FILE = 'asset:file';

export type ShareableLink = { url: string; label?: string };
export type ChannelLink = { platform: ChannelPlatform; url: string };
export type AssetRef = { media_id: string; previewUri?: string; filename?: string };

export type SplitLinks = {
  shareable: ShareableLink[];
  channel: ChannelLink[];
  video: AssetRef | null;
  file: AssetRef | null;
};

function isPlatform(value: string): value is ChannelPlatform {
  return (CHANNEL_PLATFORMS as string[]).includes(value);
}

export function splitProductLinks(
  links: { url: string; label?: string | null; sort_order?: number }[] | undefined,
): SplitLinks {
  const shareable: ShareableLink[] = [];
  const channel: ChannelLink[] = [];
  let video: AssetRef | null = null;
  let file: AssetRef | null = null;
  for (const link of links ?? []) {
    const label = String(link.label || '').trim();
    const url = String(link.url || '').trim();
    if (!url) continue;
    if (label === ASSET_VIDEO) {
      video = { media_id: url };
      continue;
    }
    if (label === ASSET_FILE) {
      file = { media_id: url };
      continue;
    }
    if (label.startsWith(CHANNEL_PREFIX)) {
      const platform = label.slice(CHANNEL_PREFIX.length).toLowerCase();
      if (isPlatform(platform)) {
        channel.push({ platform, url });
        continue;
      }
    }
    shareable.push({ url, label: label || undefined });
  }
  return { shareable, channel, video, file };
}

export function mergeProductLinks(parts: SplitLinks): {
  url: string;
  label?: string | null;
  sort_order: number;
}[] {
  const out: { url: string; label?: string | null; sort_order: number }[] = [];
  let order = 0;
  for (const row of parts.shareable) {
    const url = row.url.trim();
    if (!url) continue;
    out.push({ url, label: (row.label || '').trim() || null, sort_order: order++ });
  }
  for (const row of parts.channel) {
    const url = row.url.trim();
    if (!url) continue;
    out.push({ url, label: `${CHANNEL_PREFIX}${row.platform}`, sort_order: order++ });
  }
  if (parts.video?.media_id) {
    out.push({ url: parts.video.media_id, label: ASSET_VIDEO, sort_order: order++ });
  }
  if (parts.file?.media_id) {
    out.push({ url: parts.file.media_id, label: ASSET_FILE, sort_order: order++ });
  }
  return out;
}

export function formatProductPrice(price: string | null | undefined): string {
  const raw = String(price || '').trim();
  if (!raw) return '';
  if (raw.startsWith('$') || raw.includes(' ')) return raw;
  if (/^\d+(\.\d+)?$/.test(raw)) return `$${raw}`;
  return raw;
}

export function variantMetaLabel(product: Product): string {
  const sizes = product.sizes?.length ?? 0;
  const colors = product.colors?.length ?? 0;
  const sizePart = sizes === 1 ? '1 size' : `${sizes} sizes`;
  const colorPart = colors === 1 ? '1 color' : `${colors} colors`;
  return `${sizePart} · ${colorPart}`;
}

export function mediaSummary(product: Product): string {
  const parts = splitProductLinks(product.links);
  const images = product.images?.length ?? 0;
  const bits: string[] = [];
  bits.push(`${images} image${images === 1 ? '' : 's'}`);
  bits.push(`${parts.video ? 1 : 0} video`);
  bits.push(`${parts.file ? 1 : 0} file`);
  return bits.join(' · ');
}

export function platformLabel(platform: ChannelPlatform): string {
  switch (platform) {
    case 'instagram':
      return 'Instagram';
    case 'facebook':
      return 'Facebook';
    case 'tiktok':
      return 'TikTok';
    case 'youtube':
      return 'YouTube';
  }
}

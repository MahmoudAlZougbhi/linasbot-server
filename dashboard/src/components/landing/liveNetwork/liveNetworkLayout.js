import { IgMark, MsMark, TtMark, WaMark, WebMark } from '../channelBrandMarks';

/** Shared SVG viewBox — HTML overlays use the same % mapping. */
export const LP_NET_VB = { w: 640, h: 220 };

/**
 * Channel icon radius in viewBox units (square marks).
 * Icon CSS size = (2R / VB.w) of .lp-net width so it tracks the SVG on resize.
 */
export const LP_NET_CHANNEL_R = 16;

/**
 * Channel centers in viewBox space.
 * Line start = x + R (right edge) — must match HTML icon edge.
 */
export const LP_NET_CHANNELS = [
  { id: 'instagram', label: 'Instagram', Mark: IgMark, x: 28, y: 28 },
  { id: 'whatsapp', label: 'WhatsApp', Mark: WaMark, x: 28, y: 66 },
  { id: 'messenger', label: 'Messenger', Mark: MsMark, x: 28, y: 104 },
  { id: 'tiktok', label: 'TikTok', Mark: TtMark, x: 28, y: 142 },
  { id: 'web', label: 'Web Chat', Mark: WebMark, x: 28, y: 180 },
];

/** Right edge of a channel mark in viewBox units. */
export function lpNetLineStartX(channelX = LP_NET_CHANNELS[0].x) {
  return channelX + LP_NET_CHANNEL_R;
}

/** Replies digit center — closer to channels so flow lines reach the glyph. */
export const LP_NET_REPLIES = { x: 230, y: 104 };

/** App logo / Linas star orb. */
export const LP_NET_ORB = { x: 430, y: 110 };

/** Business count — same optical Y as replies digit center. */
export const LP_NET_BUSINESS = { x: 575, y: 104 };

/** Shared caption baseline (viewBox Y) under both digits. */
export const LP_NET_CAPTION_Y = 204;

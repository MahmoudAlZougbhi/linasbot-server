import { useId } from 'react';

/**
 * @param {{ className?: string }} props
 */
export function IgIcon({ className = 'h-5 w-5' }) {
  const uid = useId().replace(/:/g, '');
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="6.5" fill={`url(#${uid}-ig)`} />
      <rect x="5.6" y="5.6" width="12.8" height="12.8" rx="4.2" fill="none" stroke="#fff" strokeWidth="1.7" />
      <circle cx="12" cy="12" r="3.35" fill="none" stroke="#fff" strokeWidth="1.7" />
      <circle cx="16.55" cy="7.45" r="1.05" fill="#fff" />
      <defs>
        <linearGradient id={`${uid}-ig`} x1="3" y1="1" x2="21" y2="23">
          <stop stopColor="#F58529" />
          <stop offset="0.35" stopColor="#DD2A7B" />
          <stop offset="0.7" stopColor="#8134AF" />
          <stop offset="1" stopColor="#515BD4" />
        </linearGradient>
      </defs>
    </svg>
  );
}

/**
 * @param {{ className?: string }} props
 */
export function FbIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="6.5" fill="#1877F2" />
      <path
        d="M13.55 19.2v-6.35h2.14l.32-2.48h-2.46V8.8c0-.72.2-1.2 1.22-1.2h1.3V5.4c-.22-.03-1-.1-1.9-.1-1.88 0-3.17 1.15-3.17 3.26v1.81H8.55v2.48h2.45V19.2h2.55z"
        fill="#fff"
      />
    </svg>
  );
}

/**
 * @param {{ className?: string }} props
 */
export function WaIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="6.5" fill="#25D366" />
      <path
        d="M12 6.15a5.75 5.75 0 0 0-4.95 8.62L6.2 17.85l3.15-.82A5.75 5.75 0 1 0 12 6.15zm3.05 8.15c-.28.72-1.12.95-1.52.99-.38.05-.82.07-1.32-.2-.32-.16-.72-.35-1.24-.67-1.62-1.05-2.68-2.65-2.76-2.77-.1-.14-.72-.95-.72-1.8 0-.86.45-1.28.6-1.45.15-.16.33-.2.44-.2h.32c.1 0 .24 0 .37.28.14.3.46 1.12.5 1.2.05.09.07.2 0 .32-.08.12-.1.2-.2.3l-.32.38c-.1.12-.22.24-.1.42.14.18.62 1.02 1.32 1.65.82.74 1.5.98 1.72 1.08.12.06.24.05.33-.06.1-.1.38-.45.48-.6.1-.15.2-.13.34-.08.14.05.9.42 1.06.5.16.08.26.12.3.18.04.08.04.46-.12.86z"
        fill="#fff"
      />
    </svg>
  );
}

function TikTokNote({ fill, className }) {
  return (
    <path
      className={className}
      fill={fill}
      d="M14.35 6.15c.72.7 1.6 1.2 2.6 1.42v1.72c-.92-.08-1.78-.38-2.6-.88v5.55a3.52 3.52 0 1 1-2.42-3.35v1.68a1.9 1.9 0 1 0 1.32 1.8V6.15h1.1z"
    />
  );
}

/**
 * @param {{ className?: string }} props
 */
export function TtIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="6.5" fill="#111" />
      <g transform="translate(1.15 0.35)">
        <TikTokNote fill="#FE2C55" />
      </g>
      <g transform="translate(-1.15 -0.35)">
        <TikTokNote fill="#25F4EE" />
      </g>
      <TikTokNote fill="#fff" />
    </svg>
  );
}

/**
 * @param {{ className?: string }} props
 */
export function WebIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="6.5" fill="#06715F" />
      <path
        d="M6.4 8.2c0-.9.74-1.65 1.65-1.65h6.1c.9 0 1.65.74 1.65 1.65v4.15c0 .9-.74 1.65-1.65 1.65H10.2L7.7 15.9V13.7c-.8-.2-1.3-.9-1.3-1.7V8.2z"
        fill="#fff"
      />
      <path
        d="M10.3 12.55h5.55c.85 0 1.55.7 1.55 1.55v3.05c0 .7-.45 1.3-1.1 1.5v1.85l-2.2-1.85H12c-.85 0-1.55-.7-1.55-1.55v-.4"
        fill="#D7EFE8"
      />
    </svg>
  );
}

export const CHANNELS = [
  { id: 'instagram', label: 'Instagram', Icon: IgIcon },
  { id: 'facebook', label: 'Facebook', Icon: FbIcon },
  { id: 'whatsapp', label: 'WhatsApp', Icon: WaIcon },
  { id: 'tiktok', label: 'TikTok', Icon: TtIcon },
  { id: 'web', label: 'Web Chat', Icon: WebIcon },
];


import { useId } from 'react';

/** Official Instagram glyph (Simple Icons) with brand gradient. */
export function IgMark({ className = 'h-10 w-10' }) {
  const uid = useId().replace(/:/g, '');
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path
        fill={`url(#${uid}-ig)`}
        d="M12 0C8.74 0 8.333.015 7.053.072 2.695.272.273 2.69.073 7.052.014 8.333 0 8.741 0 12c0 3.259.014 3.668.072 4.948.2 4.358 2.618 6.78 6.98 6.98C8.333 23.986 8.741 24 12 24c3.259 0 3.668-.014 4.948-.072 4.354-.2 6.782-2.618 6.979-6.98.059-1.28.073-1.689.073-4.948 0-3.259-.014-3.667-.072-4.947-.196-4.354-2.617-6.78-6.979-6.98C15.668.014 15.259 0 12 0zm0 2.163c3.204 0 3.584.012 4.85.07 3.252.148 4.771 1.691 4.919 4.919.058 1.265.069 1.645.069 4.849 0 3.205-.012 3.584-.069 4.849-.149 3.225-1.664 4.771-4.919 4.919-1.266.058-1.644.07-4.85.07-3.204 0-3.584-.012-4.849-.07-3.26-.149-4.771-1.699-4.919-4.92-.058-1.265-.07-1.644-.07-4.849 0-3.204.013-3.583.07-4.849.149-3.227 1.664-4.771 4.919-4.919 1.266-.057 1.645-.069 4.849-.069zM12 5.838a6.162 6.162 0 100 12.324 6.162 6.162 0 000-12.324zM12 16a4 4 0 110-8 4 4 0 010 8zm6.406-11.845a1.44 1.44 0 100 2.881 1.44 1.44 0 000-2.881z"
      />
      <defs>
        <radialGradient id={`${uid}-ig`} cx="30%" cy="107%" r="150%">
          <stop offset="0%" stopColor="#FDF497" />
          <stop offset="5%" stopColor="#FDF497" />
          <stop offset="45%" stopColor="#FD5949" />
          <stop offset="60%" stopColor="#D6249F" />
          <stop offset="90%" stopColor="#285AEB" />
        </radialGradient>
      </defs>
    </svg>
  );
}

/** Official Facebook logo — blue circle + f. */
export function FbMark({ className = 'h-10 w-10' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="#1877F2" />
      <path
        fill="#fff"
        d="M13.14 20.04v-6.48h2.18l.33-2.53h-2.51V9.4c0-.73.2-1.23 1.25-1.23h1.34V5.91c-.23-.03-1.02-.1-1.94-.1-1.92 0-3.23 1.17-3.23 3.32v1.85H8.4v2.53h2.16v6.53h2.58z"
      />
    </svg>
  );
}

/** Official Messenger logo — bubble + lightning (Simple Icons). */
export function MsMark({ className = 'h-10 w-10' }) {
  const uid = useId().replace(/:/g, '');
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <defs>
        <linearGradient id={`${uid}-ms`} x1="0%" y1="0%" x2="100%" y2="100%">
          <stop offset="0%" stopColor="#00B2FF" />
          <stop offset="50%" stopColor="#006AFF" />
          <stop offset="100%" stopColor="#A033FF" />
        </linearGradient>
      </defs>
      <path
        fill={`url(#${uid}-ms)`}
        d="M12 0C5.373 0 0 4.974 0 11.111c0 3.498 1.744 6.614 4.469 8.65V24l4.088-2.242c1.09.301 2.246.464 3.443.464 6.627 0 12-4.974 12-11.111C24 4.974 18.627 0 12 0zm1.191 14.963l-3.055-3.26-5.963 3.26L10.733 8.1l3.13 3.26L19.754 8.1l-6.563 6.863z"
      />
    </svg>
  );
}

/** Official WhatsApp logo (Simple Icons). */
export function WaMark({ className = 'h-10 w-10' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path
        fill="#25D366"
        d="M17.472 14.382c-.297-.149-1.758-.867-2.03-.967-.273-.099-.471-.148-.67.15-.197.297-.767.966-.94 1.164-.173.199-.347.223-.644.075-.297-.15-1.255-.463-2.39-1.475-.883-.788-1.48-1.761-1.653-2.059-.173-.297-.018-.458.13-.606.134-.133.297-.347.446-.52.149-.174.198-.298.298-.497.099-.198.05-.371-.025-.52-.075-.149-.669-1.612-.916-2.207-.242-.579-.487-.5-.669-.51-.173-.008-.371-.01-.57-.01-.198 0-.52.074-.792.372-.272.297-1.04 1.016-1.04 2.479 0 1.462 1.065 2.875 1.213 3.074.149.198 2.096 3.2 5.077 4.487.709.306 1.262.489 1.694.625.712.227 1.36.195 1.871.118.571-.085 1.758-.719 2.006-1.413.248-.694.248-1.289.173-1.413-.074-.124-.272-.198-.57-.347m-5.421 7.403h-.004a9.87 9.87 0 01-5.031-1.378l-.361-.214-3.741.982.998-3.648-.235-.374a9.86 9.86 0 01-1.51-5.26c.001-5.45 4.436-9.884 9.888-9.884 2.64 0 5.122 1.03 6.988 2.898a9.825 9.825 0 012.893 6.994c-.003 5.45-4.435 9.884-9.885 9.884m8.413-18.297A11.815 11.815 0 0012.05 0C5.495 0 .16 5.335.157 11.892c0 2.096.547 4.142 1.588 5.945L.057 24l6.305-1.654a11.882 11.882 0 005.683 1.448h.005c6.554 0 11.89-5.335 11.893-11.893a11.821 11.821 0 00-3.48-8.413"
      />
    </svg>
  );
}

const TT_NOTE =
  'M12.525.02c1.31-.02 2.61-.01 3.91-.02.08 1.53.63 3.09 1.75 4.17 1.12 1.11 2.7 1.62 4.24 1.79v4.03c-1.44-.05-2.89-.35-4.2-.97-.57-.26-1.1-.59-1.62-.93-.01 2.92.01 5.84-.02 8.75-.08 1.4-.54 2.79-1.35 3.94-1.31 1.92-3.58 3.17-5.91 3.21-1.43.08-2.86-.31-4.08-1.03-2.02-1.19-3.44-3.37-3.65-5.71-.02-.5-.03-1-.01-1.49.18-1.9 1.12-3.72 2.58-4.96 1.66-1.44 3.98-2.13 6.15-1.72.02 1.48-.04 2.96-.04 4.44-.99-.32-2.15-.23-3.02.37-.63.41-1.11 1.04-1.36 1.75-.21.51-.15 1.07-.14 1.61.24 1.64 1.82 3.02 3.5 2.87 1.12-.01 2.19-.66 2.77-1.61.19-.33.4-.67.41-1.06.1-1.79.06-3.57.07-5.36.01-4.03-.01-8.05.02-12.07z';

/** Official TikTok logo (Simple Icons note + brand cyan/pink). */
export function TtMark({ className = 'h-10 w-10' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <path d={TT_NOTE} fill="#25F4EE" transform="translate(-1.15 -.35)" />
      <path d={TT_NOTE} fill="#FE2C55" transform="translate(1.15 .35)" />
      <path d={TT_NOTE} fill="#111" />
    </svg>
  );
}

/** Web Chat — Linas globe mark from the approved hero design. */
export function WebMark({ className = 'h-10 w-10' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <circle cx="12" cy="12" r="12" fill="#06715F" />
      <circle cx="12" cy="12" r="7.1" fill="none" stroke="#fff" strokeWidth="1.5" />
      <ellipse cx="12" cy="12" rx="3" ry="7.1" fill="none" stroke="#fff" strokeWidth="1.35" />
      <path d="M5.2 12h13.6M6.7 8.4h10.6M6.7 15.6h10.6" stroke="#fff" strokeWidth="1.35" />
    </svg>
  );
}

/** Hero row order: Instagram, Facebook, WhatsApp, TikTok, Web Chat. */
export const HERO_CHANNEL_MARKS = [
  { id: 'instagram', label: 'Instagram', Mark: IgMark },
  { id: 'facebook', label: 'Facebook', Mark: FbMark },
  { id: 'whatsapp', label: 'WhatsApp', Mark: WaMark },
  { id: 'tiktok', label: 'TikTok', Mark: TtMark },
  { id: 'web', label: 'Web Chat', Mark: WebMark },
];

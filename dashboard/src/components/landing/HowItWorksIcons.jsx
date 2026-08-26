/** @param {{ className?: string }} props */
export function CalendarGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <rect x="4" y="5" width="16" height="15" rx="2.4" stroke="currentColor" strokeWidth="1.7" />
      <path d="M4 10h16M8 3.6v4M16 3.6v4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function CompareGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M8 7v10M8 7l-2.4 2.4M8 7l2.4 2.4M16 17V7M16 17l-2.4-2.4M16 17l2.4-2.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function DecideGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.2" stroke="currentColor" strokeWidth="1.7" />
      <path d="m8.2 12.2 2.5 2.5 5.1-5.4" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function CommentGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M12 19.2c4.6 0 8.3-3.1 8.3-7S16.6 5.2 12 5.2 3.7 8.3 3.7 12.2c0 1.6.6 3.1 1.7 4.3L4.4 19.5 7.6 18c1.3.8 2.8 1.2 4.4 1.2Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function CoinGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <ellipse cx="12" cy="8" rx="7" ry="3.2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5 8v8c0 1.8 3.1 3.2 7 3.2s7-1.4 7-3.2V8" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5 12c0 1.8 3.1 3.2 7 3.2s7-1.4 7-3.2" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function ChatGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v7a2.5 2.5 0 0 1-2.5 2.5H11l-4 3v-3H7.5A2.5 2.5 0 0 1 5 13.5v-7Z" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function DocGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M7 4.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5.5 19V6A1.5 1.5 0 0 1 7 4.5Z" stroke="currentColor" strokeWidth="1.6" />
      <path d="M14 4.5V9h4.2M8.5 13h7M8.5 16.5h5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

export const POINT_ICONS = [CalendarGlyph, CompareGlyph, DecideGlyph];

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
      <path
        d="M8 7v10M8 7l-2.4 2.4M8 7l2.4 2.4M16 17V7M16 17l-2.4-2.4M16 17l2.4-2.4"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
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
      <path
        d="M5 6.5A2.5 2.5 0 0 1 7.5 4h9A2.5 2.5 0 0 1 19 6.5v7a2.5 2.5 0 0 1-2.5 2.5H11l-4 3v-3H7.5A2.5 2.5 0 0 1 5 13.5v-7Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function DocGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M7 4.5h7l4 4V19a1.5 1.5 0 0 1-1.5 1.5h-9.5A1.5 1.5 0 0 1 5.5 19V6A1.5 1.5 0 0 1 7 4.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path d="M14 4.5V9h4.2M8.5 13h7M8.5 16.5h5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function MenuGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M5 7h14M5 12h14M5 17h10" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function SelectGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M8 4.5h8.5A2.5 2.5 0 0 1 19 7v8.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
      <path d="m5 11 5.2 5.2L19.5 7" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function ArrowGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M5 12h12.5M13 6.5 18.5 12 13 17.5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function EyeGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M2.8 12s3.4-6.2 9.2-6.2S21.2 12 21.2 12s-3.4 6.2-9.2 6.2S2.8 12 2.8 12Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <circle cx="12" cy="12" r="2.6" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function SendGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M4.2 11.2 19.5 4.5 12.2 19.8l-1.7-6.4-6.3-2.2Z" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function TranslateGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M4.5 6.5h9M9 6.5S8 12 4.8 15.5M9 6.5s1 5.5 4.2 9" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <path d="M13.5 18.5h6.2M16.6 12.2l3.1 6.3M16.6 12.2l-3.1 6.3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function SyncGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M19.2 12a7.2 7.2 0 0 1-12.2 5.2M4.8 12A7.2 7.2 0 0 1 17 6.8"
        stroke="currentColor"
        strokeWidth="1.7"
        strokeLinecap="round"
      />
      <path d="M17.2 3.8v3.6H20.8M6.8 20.2v-3.6H3.2" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function ClockGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.2" stroke="currentColor" strokeWidth="1.7" />
      <path d="M12 8v4.4l2.8 1.8" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function PauseGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.2" stroke="currentColor" strokeWidth="1.7" />
      <path d="M10 9v6M14 9v6" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function LinkGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M9.4 14.6 14.6 9.4M8.2 11.2l-1.3 1.3a3.4 3.4 0 0 0 4.8 4.8l1.3-1.3M15.8 12.8l1.3-1.3a3.4 3.4 0 0 0-4.8-4.8l-1.3 1.3"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function SparkGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M12 3.5c.9 4.4 3.1 6.6 7.5 7.5-4.4.9-6.6 3.1-7.5 7.5-.9-4.4-3.1-6.6-7.5-7.5 4.4-.9 6.6-3.1 7.5-7.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function HandGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M8.2 11.2V7.4a1.4 1.4 0 0 1 2.8 0v3.2M11 10.2V6.6a1.4 1.4 0 0 1 2.8 0v4M13.8 10.6V7.8a1.4 1.4 0 1 1 2.8 0v6.4c0 3-2.1 5.3-5.2 5.3H12c-2.4 0-4.2-1.2-5.3-3.1L5 13.4a1.35 1.35 0 0 1 2.3-1.4l.9 1.5"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function UserGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <circle cx="12" cy="8.2" r="3.2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M5.5 19c1.4-3 3.6-4.5 6.5-4.5S16.1 16 17.5 19" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function UsersGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <circle cx="9" cy="8.4" r="2.7" stroke="currentColor" strokeWidth="1.6" />
      <path d="M3.8 18.5c1.1-2.4 2.8-3.6 5.2-3.6" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="16.2" cy="9" r="2.3" stroke="currentColor" strokeWidth="1.6" />
      <path d="M12.6 18.5c.9-2 2.3-3 4.2-3 1.7 0 3 .8 4 2.2" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function LockGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <rect x="5.5" y="10.5" width="13" height="9" rx="2" stroke="currentColor" strokeWidth="1.6" />
      <path d="M8.2 10.5V8.2a3.8 3.8 0 0 1 7.6 0v2.3" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function SlidersGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M5 8h14M5 16h14" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" />
      <circle cx="9" cy="8" r="2.2" stroke="currentColor" strokeWidth="1.6" />
      <circle cx="15" cy="16" r="2.2" stroke="currentColor" strokeWidth="1.6" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function ShieldGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M12 3.8 19 6.4v5.2c0 4.4-2.9 7.6-7 9.1-4.1-1.5-7-4.7-7-9.1V6.4L12 3.8Z"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function UpgradeGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path d="M12 18.5V6.2M7.2 10.5 12 5.5l4.8 5" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

/** @param {{ className?: string }} props */
export function SaveGlyph({ className = 'h-4 w-4' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} fill="none" aria-hidden="true">
      <path
        d="M6 4.5h9.2L19.5 9v9.5A1.5 1.5 0 0 1 18 20h-12A1.5 1.5 0 0 1 4.5 18.5v-12A2 2 0 0 1 6 4.5Z"
        stroke="currentColor"
        strokeWidth="1.6"
      />
      <path d="M8 4.8v4.4h7.2V4.8M8 20v-6.2h8V20" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round" />
    </svg>
  );
}

/** @type {Record<string, (props: { className?: string }) => JSX.Element>} */
export const POINT_ICON_BY_KEY = {
  chat: ChatGlyph,
  check: DecideGlyph,
  save: SaveGlyph,
  doc: DocGlyph,
  menu: MenuGlyph,
  select: SelectGlyph,
  arrow: ArrowGlyph,
  calendar: CalendarGlyph,
  compare: CompareGlyph,
  eye: EyeGlyph,
  send: SendGlyph,
  translate: TranslateGlyph,
  sync: SyncGlyph,
  pause: PauseGlyph,
  clock: ClockGlyph,
  link: LinkGlyph,
  spark: SparkGlyph,
  hand: HandGlyph,
  user: UserGlyph,
  users: UsersGlyph,
  lock: LockGlyph,
  sliders: SlidersGlyph,
  shield: ShieldGlyph,
  upgrade: UpgradeGlyph,
  coin: CoinGlyph,
  comment: CommentGlyph,
};

/** @deprecated prefer POINT_ICON_BY_KEY via point.icon */
export const POINT_ICONS = [CalendarGlyph, CompareGlyph, DecideGlyph];

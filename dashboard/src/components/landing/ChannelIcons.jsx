export function IgIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="7" fill="url(#lp-ig)" />
      <rect x="6" y="6" width="12" height="12" rx="4" fill="none" stroke="#fff" strokeWidth="1.6" />
      <circle cx="12" cy="12" r="3.1" fill="none" stroke="#fff" strokeWidth="1.6" />
      <circle cx="16.4" cy="7.6" r="1" fill="#fff" />
      <defs>
        <linearGradient id="lp-ig" x1="4" y1="2" x2="20" y2="22">
          <stop stopColor="#F58529" />
          <stop offset="0.5" stopColor="#DD2A7B" />
          <stop offset="1" stopColor="#8134AF" />
        </linearGradient>
      </defs>
    </svg>
  );
}

export function FbIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="7" fill="#1877F2" />
      <path d="M13.4 19v-6.1h2.05l.3-2.35H13.4V9.05c0-.68.19-1.15 1.17-1.15h1.25V5.8c-.22-.03-.96-.09-1.83-.09-1.81 0-3.05 1.1-3.05 3.13v1.75H8.7v2.35h2.24V19h2.46z" fill="#fff" />
    </svg>
  );
}

export function WaIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="7" fill="#25D366" />
      <path
        d="M12 6.3a5.6 5.6 0 0 0-4.76 8.45L6.4 17.6l3.02-.79A5.6 5.6 0 1 0 12 6.3zm2.7 7.7c-.2.55-.8.7-1.1.73-.28.04-.62.06-1.01-.16-.27-.14-.62-.3-1.07-.58-1.5-.97-2.48-2.44-2.55-2.55-.08-.12-.62-.82-.62-1.57 0-.75.39-1.12.53-1.27.13-.14.29-.18.39-.18h.28c.09 0 .22 0 .33.25.13.27.42 1.03.46 1.1.04.08.06.18 0 .28-.06.11-.09.18-.18.27l-.28.33c-.09.1-.19.21-.08.36.12.16.55.9 1.18 1.46.74.66 1.36.87 1.55.96.11.05.21.04.29-.05.08-.08.33-.39.42-.53.09-.13.18-.11.3-.07.13.05.82.39.96.46.14.07.23.1.27.16.03.07.03.4-.1.75z"
        fill="#fff"
      />
    </svg>
  );
}

export function TtIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="7" fill="#111" />
      <path d="M14.2 7.2c.55.53 1.22.93 2 .1.04 0 .08 1.18.08 1.18-.73.07-1.4-.12-2.08-.5v4.55a3.35 3.35 0 1 1-3.35-3.35c.17 0 .34.02.5.05v1.46a1.9 1.9 0 1 0 1.33 1.81V7.2h1.52z" fill="#fff" />
    </svg>
  );
}

export function WebIcon({ className = 'h-5 w-5' }) {
  return (
    <svg viewBox="0 0 24 24" className={className} aria-hidden="true">
      <rect width="24" height="24" rx="7" fill="#06715F" />
      <circle cx="12" cy="12" r="5.2" fill="none" stroke="#fff" strokeWidth="1.5" />
      <path d="M7 12h10M12 7c1.6 1.5 2.4 3.2 2.4 5s-.8 3.5-2.4 5c-1.6-1.5-2.4-3.2-2.4-5s.8-3.5 2.4-5z" fill="none" stroke="#fff" strokeWidth="1.4" />
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

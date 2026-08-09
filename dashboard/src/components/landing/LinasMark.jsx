/** Inline Linas chevron mark — refined electric-blue A without unrelated logo. */
export default function LinasMark({ className = 'h-10 w-10' }) {
  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <rect width="64" height="64" rx="16" fill="#0C1424" />
      <path
        d="M16 48 L32 14 L48 48"
        stroke="#3B8EF0"
        strokeWidth="7"
        strokeLinecap="round"
        strokeLinejoin="round"
        fill="none"
      />
    </svg>
  );
}

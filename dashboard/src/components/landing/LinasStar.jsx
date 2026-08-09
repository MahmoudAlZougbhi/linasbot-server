/** Inline emerald star used in nav wordmark / chat FAB (design ZIP brand). */
export default function LinasStar({ className = 'h-5 w-5', color = '#06715F' }) {
  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      <path
        d="M32 6 C35.2 24.5 41.2 30.5 59.5 33.5 C41.2 36.5 35.2 42.5 32 61 C28.8 42.5 22.8 36.5 4.5 33.5 C22.8 30.5 28.8 24.5 32 6Z"
        fill={color}
      />
      <circle cx="44" cy="46" r="3.5" fill="#54C7AC" />
    </svg>
  );
}

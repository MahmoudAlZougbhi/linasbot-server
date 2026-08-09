/**
 * Linas four-point star mark from the landing design ZIP (`03_BRAND_ASSETS`).
 * @param {{ className?: string, tone?: 'brand' | 'white' | 'plain' }} props
 */
export default function LinasMark({ className = 'h-8 w-8', tone = 'brand' }) {
  const star = tone === 'white' ? '#FFFFFF' : '#06715F';
  const dot = tone === 'white' ? '#54C7AC' : '#54C7AC';

  if (tone === 'plain') {
    return (
      <svg className={className} viewBox="0 0 64 64" fill="none" aria-hidden="true">
        <path
          d="M32 6 C35.2 24.5 41.2 30.5 59.5 33.5 C41.2 36.5 35.2 42.5 32 61 C28.8 42.5 22.8 36.5 4.5 33.5 C22.8 30.5 28.8 24.5 32 6Z"
          fill={star}
        />
        <circle cx="44" cy="46" r="3.5" fill={dot} />
      </svg>
    );
  }

  return (
    <svg className={className} viewBox="0 0 64 64" fill="none" aria-hidden="true">
      {tone === 'brand' && <rect width="64" height="64" rx="16" fill="#111917" />}
      <path
        d="M32 12 C34.8 27.5 39.8 32.5 55 35 C39.8 37.5 34.8 42.5 32 58 C29.2 42.5 24.2 37.5 9 35 C24.2 32.5 29.2 27.5 32 12Z"
        fill={tone === 'white' ? '#FFFFFF' : '#FFFFFF'}
      />
      <circle cx="44" cy="46" r="3.2" fill={dot} />
    </svg>
  );
}

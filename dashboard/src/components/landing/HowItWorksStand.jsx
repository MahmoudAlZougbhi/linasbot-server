import { useId } from 'react';

export default function HowItWorksStand() {
  const uid = useId().replace(/:/g, '');
  return (
    <div className="hiw-podium" aria-hidden="true">
      <svg className="hiw-podium-svg" viewBox="0 0 560 118" fill="none">
        <defs>
          <radialGradient id={`${uid}-wash`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#ecf7f3" stopOpacity="0.9" />
            <stop offset="100%" stopColor="#ecf7f3" stopOpacity="0" />
          </radialGradient>
          <radialGradient id={`${uid}-top`} cx="50%" cy="32%" r="70%">
            <stop offset="0%" stopColor="#c8dfdd" />
            <stop offset="55%" stopColor="#deeeeb" />
            <stop offset="100%" stopColor="#f3faf8" />
          </radialGradient>
          <radialGradient id={`${uid}-base`} cx="50%" cy="32%" r="70%">
            <stop offset="0%" stopColor="#daeeeb" />
            <stop offset="62%" stopColor="#e8f4f1" />
            <stop offset="100%" stopColor="#f7fffd" />
          </radialGradient>
        </defs>
        <ellipse cx="280" cy="98" rx="246" ry="18" fill={`url(#${uid}-wash)`} />
        <ellipse cx="280" cy="72" rx="206" ry="14" fill="#c8dfdd" />
        <ellipse cx="280" cy="58" rx="206" ry="16" fill={`url(#${uid}-base)`} />
        <ellipse cx="280" cy="58" rx="206" ry="16" fill="none" stroke="#f7fffd" strokeWidth="1.7" />
        <ellipse cx="280" cy="40" rx="156" ry="11" fill="#bfd9d6" />
        <ellipse cx="280" cy="28" rx="156" ry="13" fill={`url(#${uid}-top)`} />
        <ellipse cx="280" cy="28" rx="156" ry="13" fill="none" stroke="#f4fbfa" strokeWidth="1.5" />
        <ellipse cx="280" cy="24" rx="88" ry="5" fill="#9bb8b4" opacity="0.16" />
      </svg>
    </div>
  );
}

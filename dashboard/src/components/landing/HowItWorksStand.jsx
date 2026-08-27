import { useId } from 'react';

/** Karen Figma stand — flat white disc + soft mint glow under the phone. */
export default function HowItWorksStand() {
  const uid = useId().replace(/:/g, '');
  return (
    <div className="hiw-podium" aria-hidden="true">
      <svg className="hiw-podium-svg" viewBox="0 0 640 160" fill="none">
        <defs>
          <radialGradient id={`${uid}-glow`} cx="50%" cy="55%" r="50%">
            <stop offset="0%" stopColor="#9fffe0" stopOpacity="0.55" />
            <stop offset="38%" stopColor="#54c7ac" stopOpacity="0.28" />
            <stop offset="72%" stopColor="#54c7ac" stopOpacity="0.08" />
            <stop offset="100%" stopColor="#54c7ac" stopOpacity="0" />
          </radialGradient>
          <radialGradient id={`${uid}-disc`} cx="50%" cy="35%" r="68%">
            <stop offset="0%" stopColor="#ffffff" />
            <stop offset="55%" stopColor="#f7fbf9" />
            <stop offset="100%" stopColor="#e8f3ef" />
          </radialGradient>
          <radialGradient id={`${uid}-rim`} cx="50%" cy="20%" r="70%">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#d7ebe5" stopOpacity="0.55" />
          </radialGradient>
          <radialGradient id={`${uid}-contact`} cx="50%" cy="50%" r="50%">
            <stop offset="0%" stopColor="#0b3d34" stopOpacity="0.14" />
            <stop offset="55%" stopColor="#0b3d34" stopOpacity="0.05" />
            <stop offset="100%" stopColor="#0b3d34" stopOpacity="0" />
          </radialGradient>
        </defs>
        {/* Soft mint halo under the disc */}
        <ellipse cx="320" cy="118" rx="290" ry="36" fill={`url(#${uid}-glow)`} />
        {/* Disc body */}
        <ellipse cx="320" cy="92" rx="228" ry="28" fill={`url(#${uid}-disc)`} />
        <ellipse cx="320" cy="92" rx="228" ry="28" fill="none" stroke="#ffffff" strokeWidth="2.2" opacity="0.9" />
        {/* Top face highlight rim */}
        <ellipse cx="320" cy="84" rx="210" ry="20" fill={`url(#${uid}-rim)`} opacity="0.55" />
        {/* Contact shadow where the phone sits */}
        <ellipse cx="320" cy="78" rx="118" ry="10" fill={`url(#${uid}-contact)`} />
      </svg>
    </div>
  );
}

import { useId } from "react";

const DEEP = "color-mix(in srgb, var(--accent) 62%, #000)";

/**
 * The CloudNest.ai mark: a network resting in a nest (same artwork as assets/logo-mark.svg).
 * Its colours follow the theme accent (cyan in dark mode, purple in light mode).
 */
export default function LogoMark({ className = "w-6 h-6" }: { className?: string }) {
  const gradient = useId();
  return (
    <svg viewBox="0 0 256 256" className={className} role="img" aria-label="CloudNest.ai">
      <defs>
        <linearGradient id={gradient} x1="0" y1="0" x2="1" y2="1">
          <stop offset="0" style={{ stopColor: "var(--accent-bright)" }} />
          <stop offset="1" style={{ stopColor: DEEP }} />
        </linearGradient>
      </defs>
      <rect width="256" height="256" rx="60" fill={`url(#${gradient})`} />
      <g fill="none" stroke="#fff" strokeLinecap="round" strokeWidth="14">
        <path d="M44 132a84 84 0 0 0 168 0" />
        <path d="M72 132a56 56 0 0 0 112 0" opacity=".75" />
        <path d="M100 132a28 28 0 0 0 56 0" opacity=".5" />
      </g>
      <g stroke="#fff" strokeLinecap="round" strokeWidth="7" opacity=".9">
        <path d="M128 90L82 66M128 90L174 66M128 90V132" />
      </g>
      <circle cx="82" cy="66" r="10" fill="#fff" />
      <circle cx="174" cy="66" r="10" fill="#fff" />
      <circle cx="128" cy="90" r="20" fill="#fff" />
      <circle cx="128" cy="90" r="8" style={{ fill: DEEP }} />
    </svg>
  );
}

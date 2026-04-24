export function NovaIcon({ size = 32, className = "" }: { size?: number; className?: string }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 100 100"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={className}
    >
      <defs>
        <linearGradient id="nova-bg" x1="0" y1="0" x2="100" y2="100" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#050e1a" />
          <stop offset="100%" stopColor="#091c33" />
        </linearGradient>
        <radialGradient id="nova-glow" cx="50%" cy="50%" r="50%">
          <stop offset="0%" stopColor="#0ea5e9" stopOpacity="0.22" />
          <stop offset="100%" stopColor="#0ea5e9" stopOpacity="0" />
        </radialGradient>
        <linearGradient id="nova-star" x1="50" y1="12" x2="50" y2="88" gradientUnits="userSpaceOnUse">
          <stop offset="0%" stopColor="#bae6fd" />
          <stop offset="40%" stopColor="#38bdf8" />
          <stop offset="100%" stopColor="#0284c7" />
        </linearGradient>
        <filter id="nova-gf" x="-40%" y="-40%" width="180%" height="180%">
          <feGaussianBlur stdDeviation="4" />
        </filter>
      </defs>
      <rect width="100" height="100" rx="22" fill="url(#nova-bg)" />
      <circle cx="50" cy="50" r="36" fill="#0ea5e9" opacity="0.12" filter="url(#nova-gf)" />
      <path
        d="M50,12 C50,34 34,50 12,50 C34,50 50,66 50,88 C50,66 66,50 88,50 C66,50 50,34 50,12Z"
        fill="url(#nova-star)"
      />
      <path
        d="M50,28 C50,40 40,50 28,50 C40,50 50,60 50,72 C50,60 60,50 72,50 C60,50 50,40 50,28Z"
        fill="white"
        opacity="0.10"
      />
      <circle cx="50" cy="50" r="5.5" fill="white" opacity="0.88" />
      <circle cx="50" cy="50" r="2.2" fill="#bae6fd" />
    </svg>
  )
}

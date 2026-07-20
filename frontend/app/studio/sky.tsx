// The studio's sky: a generated cloudscape, no photo asset. Fractal noise
// (feTurbulence) is the classic cloud-generation algorithm — shaped into soft
// billows, tinted blue-grey duotone, with a diagonal light break and film
// grain. Rendered once as a fixed, non-interactive layer behind the console.
// A slight darkening toward the center keeps the readout/panels legible over
// whatever cloud happens to sit behind them.
export function Sky() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 select-none">
      <svg
        preserveAspectRatio="xMidYMid slice"
        viewBox="0 0 1440 900"
        className="h-full w-full"
      >
        <defs>
          <linearGradient id="sky-base" x1="0" y1="0" x2="0.35" y2="1">
            <stop offset="0" stopColor="#3d4c60" />
            <stop offset="0.5" stopColor="#2b3441" />
            <stop offset="1" stopColor="#1b2027" />
          </linearGradient>

          <linearGradient id="sky-shaft" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0.15" stopColor="#000000" stopOpacity="0" />
            <stop offset="0.42" stopColor="#54688a" stopOpacity="0.45" />
            <stop offset="0.7" stopColor="#000000" stopOpacity="0" />
          </linearGradient>

          {/* Calms the middle a little so the content column sits over
              quieter sky, while the corners and top keep the drama. Kept
              light — the panels supply their own dark backing for text. */}
          <radialGradient id="sky-calm" cx="0.5" cy="0.58" r="0.7">
            <stop offset="0" stopColor="#151a20" stopOpacity="0.38" />
            <stop offset="0.6" stopColor="#151a20" stopOpacity="0.1" />
            <stop offset="1" stopColor="#151a20" stopOpacity="0" />
          </radialGradient>

          {/* Big soft cloud billows */}
          <filter id="sky-clouds" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.0035 0.0055"
              numOctaves={6}
              seed={14}
              stitchTiles="stitch"
              result="noise"
            />
            <feColorMatrix
              in="noise"
              type="matrix"
              values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"
              result="an"
            />
            <feComponentTransfer in="an" result="cloudA">
              <feFuncA type="table" tableValues="0 0 0.05 0.25 0.55 0.85 1" />
            </feComponentTransfer>
            <feFlood floodColor="#c6d4e4" result="cloudCol" />
            <feComposite in="cloudCol" in2="cloudA" operator="in" />
          </filter>

          {/* Finer wispy detail */}
          <filter id="sky-wisps" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
            <feTurbulence
              type="fractalNoise"
              baseFrequency="0.011 0.016"
              numOctaves={5}
              seed={4}
              stitchTiles="stitch"
              result="noise"
            />
            <feColorMatrix
              in="noise"
              type="matrix"
              values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0"
              result="an"
            />
            <feComponentTransfer in="an" result="cloudA">
              <feFuncA type="table" tableValues="0 0 0 0.15 0.5 0.9" />
            </feComponentTransfer>
            <feFlood floodColor="#d3dfee" result="cloudCol" />
            <feComposite in="cloudCol" in2="cloudA" operator="in" />
          </filter>

          {/* Film grain */}
          <filter id="sky-grain" colorInterpolationFilters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={3} stitchTiles="stitch" result="g" />
            <feColorMatrix in="g" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.55 0" />
          </filter>
        </defs>

        <rect width="1440" height="900" fill="url(#sky-base)" />
        <rect width="1440" height="900" filter="url(#sky-clouds)" />
        <rect width="1440" height="900" filter="url(#sky-wisps)" opacity="0.5" />
        <rect width="1440" height="900" fill="url(#sky-shaft)" style={{ mixBlendMode: "screen" }} />
        <rect width="1440" height="900" fill="url(#sky-calm)" />
        <rect width="1440" height="900" filter="url(#sky-grain)" style={{ mixBlendMode: "overlay" }} opacity={0.5} />
      </svg>
    </div>
  );
}

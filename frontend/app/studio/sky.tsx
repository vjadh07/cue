// The studio's sky: a generated cloudscape, no photo asset. Fractal noise
// (feTurbulence) is the classic cloud-generation algorithm — shaped into soft
// billows, tinted a saturated blue duotone, with dark storm masses for depth,
// a bright light-break and diagonal shaft, and film grain. Rendered once as a
// fixed, non-interactive layer behind the console. A slight darkening toward
// the center keeps the readout/panels legible over the brighter cloud breaks.
export function Sky() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 select-none">
      <svg preserveAspectRatio="xMidYMid slice" viewBox="0 0 1440 900" className="h-full w-full">
        <defs>
          <linearGradient id="sky-base" x1="0" y1="0" x2="0.35" y2="1">
            <stop offset="0" stopColor="#41598a" />
            <stop offset="0.5" stopColor="#28374f" />
            <stop offset="1" stopColor="#131c2b" />
          </linearGradient>

          {/* Bright light-break glow, upper area — where the sun breaks through */}
          <radialGradient id="sky-glow" cx="0.62" cy="0.12" r="0.6">
            <stop offset="0" stopColor="#a9c6ea" stopOpacity="0.55" />
            <stop offset="0.5" stopColor="#7ea0cc" stopOpacity="0.18" />
            <stop offset="1" stopColor="#7ea0cc" stopOpacity="0" />
          </radialGradient>

          <linearGradient id="sky-shaft" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0.12" stopColor="#000000" stopOpacity="0" />
            <stop offset="0.42" stopColor="#93b2dc" stopOpacity="0.55" />
            <stop offset="0.68" stopColor="#000000" stopOpacity="0" />
          </linearGradient>

          {/* Calms the middle a little so the content column sits over quieter
              sky, while the corners and top keep the drama. Kept light — the
              panels supply their own dark backing for text. */}
          <radialGradient id="sky-calm" cx="0.5" cy="0.58" r="0.7">
            <stop offset="0" stopColor="#0f1622" stopOpacity="0.34" />
            <stop offset="0.6" stopColor="#0f1622" stopOpacity="0.08" />
            <stop offset="1" stopColor="#0f1622" stopOpacity="0" />
          </radialGradient>

          {/* Big soft cloud billows */}
          <filter id="sky-clouds" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.0035 0.0055" numOctaves={6} seed={14} stitchTiles="stitch" result="noise" />
            <feColorMatrix in="noise" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="an" />
            <feComponentTransfer in="an" result="cloudA">
              <feFuncA type="table" tableValues="0 0 0.02 0.3 0.72 1" />
            </feComponentTransfer>
            <feFlood floodColor="#d5e4f6" result="cloudCol" />
            <feComposite in="cloudCol" in2="cloudA" operator="in" />
          </filter>

          {/* Finer wispy detail */}
          <filter id="sky-wisps" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.011 0.016" numOctaves={5} seed={4} stitchTiles="stitch" result="noise" />
            <feColorMatrix in="noise" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="an" />
            <feComponentTransfer in="an" result="cloudA">
              <feFuncA type="table" tableValues="0 0 0 0.12 0.55 1" />
            </feComponentTransfer>
            <feFlood floodColor="#e6f0fb" result="cloudCol" />
            <feComposite in="cloudCol" in2="cloudA" operator="in" />
          </filter>

          {/* Dark storm masses — deepen some regions so the brights have depth */}
          <filter id="sky-dark" x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.0028 0.0042" numOctaves={5} seed={21} stitchTiles="stitch" result="noise" />
            <feColorMatrix in="noise" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="an" />
            <feComponentTransfer in="an" result="cloudA">
              <feFuncA type="table" tableValues="0 0 0 0.1 0.4 0.75" />
            </feComponentTransfer>
            <feFlood floodColor="#0e1522" result="cloudCol" />
            <feComposite in="cloudCol" in2="cloudA" operator="in" />
          </filter>

          {/* Film grain */}
          <filter id="sky-grain" colorInterpolationFilters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.9" numOctaves={2} seed={3} stitchTiles="stitch" result="g" />
            <feColorMatrix in="g" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.5 0" />
          </filter>
        </defs>

        <rect width="1440" height="900" fill="url(#sky-base)" />
        <rect width="1440" height="900" filter="url(#sky-dark)" opacity={0.9} />
        <rect width="1440" height="900" filter="url(#sky-clouds)" />
        <rect width="1440" height="900" filter="url(#sky-wisps)" opacity={0.55} />
        <rect width="1440" height="900" fill="url(#sky-glow)" style={{ mixBlendMode: "screen" }} />
        <rect width="1440" height="900" fill="url(#sky-shaft)" style={{ mixBlendMode: "screen" }} />
        <rect width="1440" height="900" fill="url(#sky-calm)" />
        <rect width="1440" height="900" filter="url(#sky-grain)" style={{ mixBlendMode: "overlay" }} opacity={0.5} />
      </svg>
    </div>
  );
}

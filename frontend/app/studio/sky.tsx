// The studio's sky: a generated cloudscape, no photo asset. Fractal noise
// (feTurbulence) is the classic cloud-generation algorithm — stretched into
// soft horizontal cloud rows over a bright cerulean sky, with a subtle canvas
// tooth. Rendered once as a fixed, non-interactive layer behind the console.
export function Sky() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 select-none">
      <svg preserveAspectRatio="xMidYMid slice" viewBox="0 0 1440 900" className="h-full w-full">
        <defs>
          <linearGradient id="sky-base" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#6fabec" />
            <stop offset="0.6" stopColor="#5b9be6" />
            <stop offset="1" stopColor="#6aa6ea" />
          </linearGradient>

          <radialGradient id="sky-glow" cx="0.5" cy="0.05" r="0.9">
            <stop offset="0" stopColor="#eaf3fd" stopOpacity="0.45" />
            <stop offset="0.6" stopColor="#cfe4fb" stopOpacity="0" />
          </radialGradient>

          {/* Big soft clouds in horizontal rows, with open sky between */}
          <filter id="sky-clouds" x="-5%" y="-5%" width="110%" height="110%" colorInterpolationFilters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.004 0.011" numOctaves={4} seed={11} stitchTiles="stitch" result="n" />
            <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="a" />
            <feComponentTransfer in="a" result="s">
              <feFuncA type="table" tableValues="0 0 0 0 0.15 0.55 1" />
            </feComponentTransfer>
            <feGaussianBlur in="s" stdDeviation="3.5" result="soft" />
            <feFlood floodColor="#ffffff" result="c" />
            <feComposite in="c" in2="soft" operator="in" />
          </filter>

          {/* A second, wispier row layer for variety */}
          <filter id="sky-clouds2" x="-5%" y="-5%" width="110%" height="110%" colorInterpolationFilters="sRGB">
            <feTurbulence type="fractalNoise" baseFrequency="0.006 0.016" numOctaves={3} seed={27} stitchTiles="stitch" result="n" />
            <feColorMatrix in="n" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="a" />
            <feComponentTransfer in="a" result="s">
              <feFuncA type="table" tableValues="0 0 0 0 0.1 0.4 0.85" />
            </feComponentTransfer>
            <feGaussianBlur in="s" stdDeviation="2.5" result="soft" />
            <feFlood floodColor="#f2f8ff" result="c" />
            <feComposite in="c" in2="soft" operator="in" />
          </filter>

          {/* Canvas tooth — the painted-on-fabric texture */}
          <filter id="sky-canvas" colorInterpolationFilters="sRGB">
            <feTurbulence type="turbulence" baseFrequency="0.6 0.6" numOctaves={1} seed={2} stitchTiles="stitch" result="g" />
            <feColorMatrix in="g" type="matrix" values="0 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 0.4 0" />
          </filter>
        </defs>

        <rect width="1440" height="900" fill="url(#sky-base)" />
        <rect width="1440" height="900" fill="url(#sky-glow)" />
        <rect width="1440" height="900" filter="url(#sky-clouds)" />
        <rect width="1440" height="900" filter="url(#sky-clouds2)" opacity={0.75} />
        <rect width="1440" height="900" filter="url(#sky-canvas)" style={{ mixBlendMode: "soft-light" }} opacity={0.5} />
      </svg>
    </div>
  );
}

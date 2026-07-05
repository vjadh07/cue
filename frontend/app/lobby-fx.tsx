// The lobby's interactive effects, inspired by reactbits.dev: a cursor-reactive
// grid (their DotGrid, but it's our cutting mat coming alive), variable-font
// proximity text, scramble-cycling tag text, spotlight cards, scroll reveals,
// and the equalizer ribbon. Everything runs on rAF + direct style writes — no
// animation library, no React re-renders on pointer moves — and every effect
// sits still under prefers-reduced-motion.
"use client";

import { useEffect, useRef, useState } from "react";

function prefersReducedMotion() {
  return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

/* ------------------------------------------------------------------ */
/* Aurora — three soft color washes drifting under the grid, so the    */
/* paper reads as daylight instead of a flat white sheet.              */
/* ------------------------------------------------------------------ */

export function Aurora() {
  return (
    <div aria-hidden="true" className="lobby-aurora pointer-events-none fixed inset-0 overflow-hidden">
      <span className="aurora-a" />
      <span className="aurora-b" />
      <span className="aurora-c" />
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* WaveField — the lobby's background: horizontal sound-waves drifting  */
/* across the page (reactbits' Waves, redrawn as audio). Lines undulate */
/* slowly on their own and bend toward the cursor, with a warm pool of  */
/* light where you point. Reduced motion gets one static drawing.       */
/* ------------------------------------------------------------------ */

const WAVE_LINES = 18;
const WAVE_STEP = 12; // px between sample points along each line

export function WaveField() {
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const ctx = canvas.getContext("2d");
    if (!ctx) return;

    const reduce = prefersReducedMotion();
    let raf = 0;
    let w = 0;
    let h = 0;
    const target = { x: -9999, y: -9999 };
    const pos = { x: -9999, y: -9999 };
    let energy = 0;
    let active = false;

    function resize() {
      if (!canvas || !ctx) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    }
    resize();

    function drawFrame(t: number) {
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);

      // A soft warm pool of light where the cursor rests.
      if (energy > 0.01) {
        ctx.globalAlpha = energy;
        const halo = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, 320);
        halo.addColorStop(0, "rgba(242, 191, 76, 0.13)");
        halo.addColorStop(1, "rgba(242, 191, 76, 0)");
        ctx.fillStyle = halo;
        ctx.fillRect(pos.x - 320, pos.y - 320, 640, 640);
        ctx.globalAlpha = 1;
      }

      ctx.lineWidth = 1;
      ctx.strokeStyle = "rgba(42, 56, 51, 0.10)";
      for (let i = 0; i < WAVE_LINES; i += 1) {
        const baseY = ((i + 0.5) / WAVE_LINES) * h;
        ctx.beginPath();
        for (let x = 0; x <= w + WAVE_STEP; x += WAVE_STEP) {
          // Two slow sines per line, out of phase line-to-line, so the field
          // rolls like a quiet room tone rather than a synchronized ripple.
          let y =
            baseY +
            8 * Math.sin(x * 0.006 + t * 0.00058 + i * 0.72) +
            12 * Math.sin(x * 0.0021 - t * 0.00041 + i * 1.31);
          if (energy > 0.01) {
            // Lines lean gently toward the cursor, amplitude swelling nearby.
            const dx = x - pos.x;
            const dy = baseY - pos.y;
            const gauss = Math.exp(-(dx * dx + dy * dy) / 52000) * energy;
            y += (pos.y - y) * 0.32 * gauss;
            y += 6 * gauss * Math.sin(x * 0.05 + t * 0.004);
          }
          if (x === 0) ctx.moveTo(x, y);
          else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
    }

    if (reduce) {
      // One still drawing — the texture without the motion.
      drawFrame(0);
      window.addEventListener("resize", () => {
        resize();
        drawFrame(0);
      });
      return;
    }

    function onMove(e: PointerEvent) {
      target.x = e.clientX;
      target.y = e.clientY;
      if (!active) {
        pos.x = e.clientX;
        pos.y = e.clientY;
        active = true;
      }
    }
    function onLeave() {
      active = false;
    }

    function loop(t: number) {
      raf = requestAnimationFrame(loop);
      pos.x += (target.x - pos.x) * 0.1;
      pos.y += (target.y - pos.y) * 0.1;
      energy += ((active ? 1 : 0) - energy) * 0.06;
      drawFrame(t);
    }
    raf = requestAnimationFrame(loop);

    window.addEventListener("pointermove", onMove);
    document.documentElement.addEventListener("mouseleave", onLeave);
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      document.documentElement.removeEventListener("mouseleave", onLeave);
      window.removeEventListener("resize", resize);
    };
  }, []);

  return (
    <canvas
      ref={canvasRef}
      aria-hidden="true"
      className="pointer-events-none fixed inset-0 h-full w-full"
    />
  );
}

/* ------------------------------------------------------------------ */
/* Entrance staging — the hero blur-rises in on load. SSR paints        */
/* everything visible (no-JS safe); on mount we snap to the hidden      */
/* "pre" state for two frames, then release the transition.             */
/* ------------------------------------------------------------------ */

export function useEntranceStage(): "ssr" | "set" | "live" {
  const [stage, setStage] = useState<"ssr" | "set" | "live">("ssr");
  useEffect(() => {
    if (prefersReducedMotion()) {
      setStage("live");
      return;
    }
    setStage("set");
    let raf2 = 0;
    const raf1 = requestAnimationFrame(() => {
      raf2 = requestAnimationFrame(() => setStage("live"));
    });
    return () => {
      cancelAnimationFrame(raf1);
      cancelAnimationFrame(raf2);
    };
  }, []);
  return stage;
}

/* ------------------------------------------------------------------ */
/* ProximityText — headline letters gain font weight as the cursor      */
/* approaches (reactbits' VariableProximity; Geist is a variable font,  */
/* so the swell is native). Reads all rects first, then writes, so the  */
/* loop forces at most one reflow per frame.                            */
/* ------------------------------------------------------------------ */

export function ProximityText({
  text,
  className = "",
  stage,
  baseDelay = 0,
  letterStagger = 26,
}: {
  text: string;
  className?: string;
  /** Entrance stage from useEntranceStage — letters blur-rise in one by one. */
  stage?: "ssr" | "set" | "live";
  baseDelay?: number;
  letterStagger?: number;
}) {
  const wrapRef = useRef<HTMLSpanElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || prefersReducedMotion()) return;
    const letters = Array.from(wrap.querySelectorAll<HTMLSpanElement>("[data-prox]"));
    if (!letters.length) return;

    let raf = 0;
    const cursor = { x: -9999, y: -9999 };
    let settled = false;

    function onMove(e: PointerEvent) {
      cursor.x = e.clientX;
      cursor.y = e.clientY;
    }
    window.addEventListener("pointermove", onMove);

    function loop() {
      raf = requestAnimationFrame(loop);
      const bounds = wrap!.getBoundingClientRect();
      const near =
        cursor.x > bounds.left - 200 &&
        cursor.x < bounds.right + 200 &&
        cursor.y > bounds.top - 200 &&
        cursor.y < bounds.bottom + 200;
      if (!near) {
        if (!settled) {
          letters.forEach((el) => (el.style.fontVariationSettings = '"wght" 600'));
          settled = true;
        }
        return;
      }
      settled = false;
      const rects = letters.map((el) => el.getBoundingClientRect());
      letters.forEach((el, i) => {
        const r = rects[i];
        const dx = r.left + r.width / 2 - cursor.x;
        const dy = r.top + r.height / 2 - cursor.y;
        const weight = 600 + 300 * Math.exp(-(dx * dx + dy * dy) / 22000);
        el.style.fontVariationSettings = `"wght" ${Math.round(weight)}`;
      });
    }
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
    };
  }, []);

  const pre = stage === "set" ? " pre" : "";
  return (
    <span ref={wrapRef} className={className}>
      {Array.from(text).map((ch, i) =>
        ch === " " ? (
          " "
        ) : (
          <span
            key={i}
            data-prox
            className={`lobby-rise-letter inline-block${pre}`}
            style={stage ? { transitionDelay: `${baseDelay + i * letterStagger}ms` } : undefined}
          >
            {ch}
          </span>
        ),
      )}
    </span>
  );
}

/* ------------------------------------------------------------------ */
/* TagCycler — the headline chip cycles its word with a scramble that   */
/* resolves left-to-right (reactbits' DecryptedText). Reduced motion    */
/* gets a plain swap, no flashing.                                      */
/* ------------------------------------------------------------------ */

const SCRAMBLE_CHARS = "abcdefghijklmnopqrstuvwxyz";

export function TagCycler({ words, interval = 3200 }: { words: string[]; interval?: number }) {
  const [text, setText] = useState(words[0]);

  useEffect(() => {
    let index = 0;
    let scramble: ReturnType<typeof setInterval> | undefined;
    const reduce = prefersReducedMotion();

    const cycle = setInterval(() => {
      index = (index + 1) % words.length;
      const word = words[index];
      if (reduce) {
        setText(word);
        return;
      }
      if (scramble) clearInterval(scramble);
      let frame = 0;
      const frames = word.length + 5;
      scramble = setInterval(() => {
        frame += 1;
        const resolved = Math.floor((frame / frames) * word.length);
        let next = word.slice(0, resolved);
        for (let i = resolved; i < word.length; i += 1) {
          next += SCRAMBLE_CHARS[Math.floor(Math.random() * SCRAMBLE_CHARS.length)];
        }
        setText(next);
        if (frame >= frames) {
          if (scramble) clearInterval(scramble);
          setText(word);
        }
      }, 36);
    }, interval);

    return () => {
      clearInterval(cycle);
      if (scramble) clearInterval(scramble);
    };
  }, [words, interval]);

  return <>{text}</>;
}

/* ------------------------------------------------------------------ */
/* SpotlightCard — a warm pool of light follows the cursor inside the   */
/* card (reactbits' SpotlightCard). Pure CSS vars; the ::before layer   */
/* lives in globals.css.                                                */
/* ------------------------------------------------------------------ */

export function SpotlightCard({
  className = "",
  children,
}: {
  className?: string;
  children: React.ReactNode;
}) {
  function onMove(e: React.PointerEvent<HTMLDivElement>) {
    const rect = e.currentTarget.getBoundingClientRect();
    e.currentTarget.style.setProperty("--sx", `${e.clientX - rect.left}px`);
    e.currentTarget.style.setProperty("--sy", `${e.clientY - rect.top}px`);
  }
  return (
    <div onPointerMove={onMove} className={`lobby-spot-card ${className}`}>
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* Reveal — below-fold sections blur-rise in as they enter the          */
/* viewport. Content is visible by default (SSR, no-JS, headless);      */
/* only mounted JS pre-hides what's still below the fold.               */
/* ------------------------------------------------------------------ */

export function Reveal({
  children,
  delay = 0,
  className = "",
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
}) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el || prefersReducedMotion()) return;
    // Never re-hide something the visitor can already see.
    if (el.getBoundingClientRect().top < window.innerHeight * 0.92) return;
    el.classList.add("pre");
    const io = new IntersectionObserver(
      (entries) => {
        if (entries[0].isIntersecting) {
          el.classList.remove("pre");
          io.disconnect();
        }
      },
      { rootMargin: "0px 0px -80px 0px" },
    );
    io.observe(el);
    return () => io.disconnect();
  }, []);

  return (
    <div
      ref={ref}
      className={`lobby-reveal ${className}`}
      style={delay ? { transitionDelay: `${delay}ms` } : undefined}
    >
      {children}
    </div>
  );
}

/* ------------------------------------------------------------------ */
/* EqRibbon — the level meter under the hero. Bars breathe on a slow    */
/* sine when idle and rise under the cursor like a fader sweep.         */
/* ------------------------------------------------------------------ */

const EQ_BARS = 56;

function restingScale(i: number) {
  return 0.22 + 0.14 * Math.abs(Math.sin(i * 0.9)) + 0.1 * Math.abs(Math.sin(i * 0.23));
}

export function EqRibbon() {
  const barsRef = useRef<(HTMLSpanElement | null)[]>([]);
  const wrapRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const wrap = wrapRef.current;
    if (!wrap || prefersReducedMotion()) return;

    let raf = 0;
    let visible = true;
    const cursor = { x: 0.5, active: false };
    let energy = 0;

    const io = new IntersectionObserver(([entry]) => {
      visible = entry.isIntersecting;
    });
    io.observe(wrap);

    function onMove(e: PointerEvent) {
      const rect = wrap!.getBoundingClientRect();
      cursor.x = (e.clientX - rect.left) / rect.width;
      cursor.active = true;
    }
    function onLeave() {
      cursor.active = false;
    }
    wrap.addEventListener("pointermove", onMove);
    wrap.addEventListener("pointerleave", onLeave);

    function loop(t: number) {
      raf = requestAnimationFrame(loop);
      if (!visible) return;
      energy += ((cursor.active ? 1 : 0) - energy) * 0.1;
      barsRef.current.forEach((bar, i) => {
        if (!bar) return;
        const idle = 0.05 * Math.sin(t / 640 + i * 0.42);
        const center = (i + 0.5) / EQ_BARS;
        const dist = Math.abs(center - cursor.x);
        const boost = energy * Math.exp(-(dist * dist) / 0.004) * 0.85;
        const scale = Math.min(1, Math.max(0.08, restingScale(i) + idle + boost));
        bar.style.transform = `scaleY(${scale})`;
      });
    }
    raf = requestAnimationFrame(loop);

    return () => {
      cancelAnimationFrame(raf);
      io.disconnect();
      wrap.removeEventListener("pointermove", onMove);
      wrap.removeEventListener("pointerleave", onLeave);
    };
  }, []);

  return (
    <div
      ref={wrapRef}
      aria-hidden="true"
      className="mx-auto flex h-16 w-full max-w-2xl items-end gap-[3px] px-2"
    >
      {Array.from({ length: EQ_BARS }).map((_, i) => (
        <span
          key={i}
          ref={(el) => {
            barsRef.current[i] = el;
          }}
          className="h-full flex-1 origin-bottom rounded-sm bg-cue-press/70 will-change-transform"
          style={{ transform: `scaleY(${restingScale(i)})` }}
        />
      ))}
    </div>
  );
}

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
/* AsciiField — the lobby's background: a full-viewport field of tiny   */
/* mono characters rendering sound propagating through the room. Two    */
/* off-stage "speakers" send slow ambient ripples across the paper; the */
/* cursor is a live sound source (ripples radiate from it, in amber),   */
/* and a click emits a one-shot pulse that travels outward. Character   */
/* density follows the wave: blank → · : ~ + x % # with ♪ at the        */
/* loudest crests. Glyphs are pre-baked to sprite tiles so each frame   */
/* is pure drawImage. Reduced motion gets one still drawing.            */
/* ------------------------------------------------------------------ */

const RAMP = ["·", ":", "~", "+", "x", "%", "#"];
const NOTES = ["♪", "♫"];
const CELL_W = 14;
const CELL_H = 16;
const FLOOR = 0.44; // field values below this render as blank paper

type Pulse = { x: number; y: number; t0: number };

export function AsciiField() {
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
    let cols = 0;
    let rows = 0;
    let frame = 0;
    const target = { x: -9999, y: -9999 };
    const pos = { x: -9999, y: -9999 };
    let energy = 0;
    let active = false;
    let pulses: Pulse[] = [];

    // Every glyph is baked once (ink + amber variants); frames only blit.
    let ink: HTMLCanvasElement[] = [];
    let hot: HTMLCanvasElement[] = [];

    function bake(dpr: number) {
      const glyphs = [...RAMP, ...NOTES];
      const make = (ch: string, color: string) => {
        const tile = document.createElement("canvas");
        tile.width = CELL_W * dpr;
        tile.height = CELL_H * dpr;
        const g = tile.getContext("2d")!;
        g.scale(dpr, dpr);
        g.font = "12px ui-monospace, Menlo, monospace";
        g.textAlign = "center";
        g.textBaseline = "middle";
        g.fillStyle = color;
        g.fillText(ch, CELL_W / 2, CELL_H / 2 + 1);
        return tile;
      };
      ink = glyphs.map((ch) => make(ch, "rgba(42, 56, 51, 0.14)"));
      hot = glyphs.map((ch) => make(ch, "rgba(151, 103, 21, 0.32)"));
    }

    function resize() {
      if (!canvas || !ctx) return;
      const dpr = Math.min(window.devicePixelRatio || 1, 2);
      w = window.innerWidth;
      h = window.innerHeight;
      cols = Math.ceil(w / CELL_W);
      rows = Math.ceil(h / CELL_H);
      canvas.width = w * dpr;
      canvas.height = h * dpr;
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      bake(dpr);
    }
    resize();

    function drawFrame(t: number) {
      if (!ctx) return;
      ctx.clearRect(0, 0, w, h);

      // The two ambient sources sit just off-stage, like monitors at the
      // edges of a room, so their ripples arc across the whole page.
      const s1x = w * 0.12;
      const s1y = h * 1.08;
      const s2x = w * 0.92;
      const s2y = -h * 0.12;

      for (let row = 0; row < rows; row += 1) {
        const cy = row * CELL_H + CELL_H / 2;
        for (let col = 0; col < cols; col += 1) {
          const cx = col * CELL_W + CELL_W / 2;

          const d1 = Math.hypot(cx - s1x, cy - s1y);
          const d2 = Math.hypot(cx - s2x, cy - s2y);
          let v =
            0.5 +
            0.26 * Math.sin(d1 * 0.014 - t * 0.0011) +
            0.2 * Math.sin(d2 * 0.0095 + t * 0.00082);

          // The cursor as a live source: standing ripples around it.
          let heat = 0;
          if (energy > 0.01) {
            const dc = Math.hypot(cx - pos.x, cy - pos.y);
            const damp = Math.exp(-dc / 380) * energy;
            v += Math.sin(dc * 0.045 - t * 0.006) * 0.6 * damp;
            heat = damp;
          }

          // One-shot click pulses: a wavefront travelling outward.
          for (const p of pulses) {
            const age = t - p.t0;
            const dp = Math.hypot(cx - p.x, cy - p.y);
            const front = dp - age * 0.34;
            v += Math.exp(-(front * front) / 5200) * Math.exp(-age / 900) * 0.9;
          }

          if (v < FLOOR) continue;
          let idx = Math.min(RAMP.length - 1, Math.floor(((v - FLOOR) / (1 - FLOOR)) * RAMP.length));
          // The loudest crests occasionally sing.
          if (v > 0.92 && (col * 928371 + row * 123457) % 97 > 82) {
            idx = RAMP.length + ((col + row) % NOTES.length);
          }
          const tiles = heat > 0.18 ? hot : ink;
          ctx.drawImage(tiles[idx], col * CELL_W, row * CELL_H, CELL_W, CELL_H);
        }
      }
    }

    if (reduce) {
      drawFrame(0);
      const onResize = () => {
        resize();
        drawFrame(0);
      };
      window.addEventListener("resize", onResize);
      return () => window.removeEventListener("resize", onResize);
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
    function onDown(e: PointerEvent) {
      pulses.push({ x: e.clientX, y: e.clientY, t0: performance.now() });
      if (pulses.length > 4) pulses = pulses.slice(-4);
    }

    function loop(t: number) {
      raf = requestAnimationFrame(loop);
      frame += 1;
      if (frame % 2) return; // 30fps is plenty for a texture this slow
      pos.x += (target.x - pos.x) * 0.14;
      pos.y += (target.y - pos.y) * 0.14;
      energy += ((active ? 1 : 0) - energy) * 0.07;
      pulses = pulses.filter((p) => t - p.t0 < 3200);
      drawFrame(t);
    }
    raf = requestAnimationFrame(loop);

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerdown", onDown);
    document.documentElement.addEventListener("mouseleave", onLeave);
    window.addEventListener("resize", resize);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerdown", onDown);
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

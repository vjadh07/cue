// A guided tour of the studio: a spotlight walks the real controls in order,
// each with a short "what to do here" card. Shown once on a first visit and
// reopenable any time from the header. Anchors target live elements by a
// `data-tour` attribute (or id), so the tour tracks the actual layout.
//
// Movement is driven by a single requestAnimationFrame loop that eases the
// spotlight toward its target every frame (writing styles straight to the DOM,
// no per-frame React renders). So the spotlight *rides* the scroll to the next
// control and glides between steps, instead of snapping, waiting on a timer,
// then snapping again.
"use client";

import { useCallback, useEffect, useRef, useState } from "react";

type Step = { sel?: string; title: string; body: string };

// Steps anchor only to controls that are ALWAYS present (before you press
// Direct). The first and last cards are centered overviews with no anchor,
// so the tour teaches the whole arc without depending on post-Direct elements.
const STEPS: Step[] = [
  {
    title: "Welcome to the studio",
    body: "Cue turns a script plus one plain-English note into a performed voice track you can download. Here's the whole flow, step by step.",
  },
  {
    sel: '[data-tour="stages"]',
    title: "Know where you are",
    body: "This strip always shows the four stages: write, direct, cast & retake, produce. The lit one is where you are, with a hint for the next move.",
  },
  {
    sel: '[data-tour="voice"]',
    title: "Optional: use your own voice",
    body: "Record about 30 seconds and Cue clones your voice, entirely on this machine. Then you can cast yourself as any character.",
  },
  {
    sel: '[data-tour="script"]',
    title: "1. Write the script",
    body: "Type or paste lines here, one per row. New to it? Press “Load a sample scene”. Start a line with NAME: for a conversation, or import a .fountain screenplay.",
  },
  {
    sel: "#direction",
    title: "2. Give one direction",
    body: "Say what you want in plain English for the whole scene, like “build from calm to furious”. That's the note the brain performs to.",
  },
  {
    sel: '[data-tour="direct"]',
    title: "3. Direct it",
    body: "Press Direct. Cue reads the whole script and marks up every line for where it sits in the emotional arc.",
  },
  {
    title: "4. Play, retake, produce",
    body: "Each line gets a Play button and a note field for retakes (“again, colder”). The Booth chart shows the arc, planned vs what Cue actually performed. Finally, “Play full read” stitches one track you download as an mp3 with subtitles.",
  },
];

const PAD = 8; // breathing room around the highlighted element
const EASE = 0.22; // per-frame glide toward the target (1 = instant)

type Box = { top: number; left: number; width: number; height: number };

export function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [i, setI] = useState(0);

  const spotRef = useRef<HTMLDivElement>(null);
  const dimRef = useRef<HTMLDivElement>(null);
  const cardRef = useRef<HTMLDivElement>(null);
  const cur = useRef<Box | null>(null); // the eased position, animated each frame
  const iRef = useRef(0);

  const last = i === STEPS.length - 1;
  const step = STEPS[i];

  useEffect(() => {
    iRef.current = i;
  }, [i]);

  const finish = useCallback(() => {
    setI(0);
    onClose();
  }, [onClose]);

  const go = useCallback((next: number) => {
    setI(Math.max(0, Math.min(STEPS.length - 1, next)));
  }, []);

  // Reset to the first step whenever the tour is (re)opened.
  useEffect(() => {
    if (open) {
      setI(0);
      cur.current = null;
    }
  }, [open]);

  // On each step, scroll its element to the middle of the screen; the rAF loop
  // below then follows it there in real time.
  useEffect(() => {
    if (!open || !step.sel) return;
    const el = document.querySelector(step.sel);
    if (!el) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
  }, [open, i, step.sel]);

  // The animation loop: one rAF while the tour is open. It reads the current
  // step (via a ref, so it never goes stale) and eases the spotlight and card
  // toward the live element every frame.
  useEffect(() => {
    if (!open) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const ease = reduce ? 1 : EASE;
    let raf = 0;

    const frame = () => {
      raf = requestAnimationFrame(frame);
      const card = cardRef.current;
      const spot = spotRef.current;
      const dim = dimRef.current;
      if (!card) return;

      const active = STEPS[iRef.current];
      const el = active.sel ? document.querySelector(active.sel) : null;
      const cw = card.offsetWidth;
      const ch = card.offsetHeight;

      if (!el) {
        // Anchor-less overview step: full dim, centered card, no spotlight.
        if (spot) spot.style.opacity = "0";
        if (dim) dim.style.opacity = "1";
        card.style.top = `${Math.round(window.innerHeight / 2 - ch / 2)}px`;
        card.style.left = `${Math.round(window.innerWidth / 2 - cw / 2)}px`;
        card.style.opacity = "1";
        cur.current = null; // so the next anchored step eases in from itself
        return;
      }

      const r = el.getBoundingClientRect();
      const target: Box = { top: r.top, left: r.left, width: r.width, height: r.height };
      if (!cur.current) {
        cur.current = { ...target }; // first anchored frame: snap, don't glide from afar
      } else {
        cur.current.top += (target.top - cur.current.top) * ease;
        cur.current.left += (target.left - cur.current.left) * ease;
        cur.current.width += (target.width - cur.current.width) * ease;
        cur.current.height += (target.height - cur.current.height) * ease;
      }
      const c = cur.current;

      if (spot) {
        spot.style.opacity = "1";
        spot.style.top = `${c.top - PAD}px`;
        spot.style.left = `${c.left - PAD}px`;
        spot.style.width = `${c.width + PAD * 2}px`;
        spot.style.height = `${c.height + PAD * 2}px`;
      }
      if (dim) dim.style.opacity = "0"; // the spotlight's box-shadow does the dimming

      // Card sits below the element if it fits, otherwise above; clamped to the
      // viewport. Positioned from the eased box so it glides along too.
      const gap = 14;
      const fitsBelow = c.top + c.height + gap + ch <= window.innerHeight - 12;
      const top = fitsBelow ? c.top + c.height + gap : Math.max(12, c.top - gap - ch);
      const left = Math.min(Math.max(12, c.left), window.innerWidth - cw - 12);
      card.style.top = `${Math.round(top)}px`;
      card.style.left = `${Math.round(left)}px`;
      card.style.opacity = "1";
    };

    raf = requestAnimationFrame(frame);
    return () => cancelAnimationFrame(raf);
  }, [open]);

  // Keyboard: arrows navigate, Enter advances, Escape leaves.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
      else if (e.key === "ArrowRight" || e.key === "Enter") go(iRef.current + 1);
      else if (e.key === "ArrowLeft") go(iRef.current - 1);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, finish, go]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[200]" role="dialog" aria-modal="true" aria-label="Studio tour">
      {/* Full-screen dim for centered steps; also the click-blocker so the
          studio underneath can't be used mid-tour. Only opacity transitions —
          the rAF loop owns position, so it must not animate. */}
      <div
        ref={dimRef}
        className="fixed inset-0 bg-black/[0.66] transition-opacity duration-200"
        style={{ opacity: 0 }}
      />

      {/* The spotlight: a giant box-shadow darkens everything but this box. */}
      <div
        ref={spotRef}
        className="pointer-events-none fixed rounded-md ring-2 ring-cue transition-opacity duration-200"
        style={{ boxShadow: "0 0 0 9999px rgba(0,0,0,0.66)", opacity: 0 }}
      />

      {/* The step card. */}
      <div
        ref={cardRef}
        className="fixed z-[201] w-[min(340px,calc(100vw-24px))] rounded border border-cue-deep bg-panel p-4 shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
        style={{ top: 0, left: 0, opacity: 0 }}
      >
        <div className="flex items-baseline justify-between gap-3">
          <h3 className="text-sm font-semibold text-ink">{step.title}</h3>
          <span className="font-mono text-[10px] text-ink-3">
            {i + 1}/{STEPS.length}
          </span>
        </div>
        <p className="mt-2 text-sm leading-relaxed text-ink-2">{step.body}</p>

        <div className="mt-4 flex items-center justify-between">
          <button
            onClick={finish}
            className="font-mono text-[11px] uppercase tracking-[0.1em] text-ink-3 transition-colors hover:text-ink-2"
          >
            Skip
          </button>
          <div className="flex items-center gap-2">
            {i > 0 && (
              <button
                onClick={() => go(i - 1)}
                className="rounded border border-edge px-3 py-1.5 font-mono text-xs text-ink-2 transition-colors hover:border-edge-strong"
              >
                Back
              </button>
            )}
            <button
              onClick={() => (last ? finish() : go(i + 1))}
              className="rounded border border-cue-deep bg-cue px-3 py-1.5 text-xs font-semibold text-cue-ink transition-colors hover:bg-cue-bright"
            >
              {last ? "Start creating" : "Next"}
            </button>
          </div>
        </div>
      </div>
    </div>
  );
}

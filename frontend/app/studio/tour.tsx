// A guided tour of the studio: a spotlight walks the real controls in order,
// each with a short "what to do here" card. Shown once on a first visit and
// reopenable any time from the header. Anchors target live elements by a
// `data-tour` attribute (or id), so the tour tracks the actual layout.
"use client";

import { useCallback, useEffect, useLayoutEffect, useRef, useState } from "react";

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

export function Tour({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [i, setI] = useState(0);
  const [rect, setRect] = useState<DOMRect | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number; centered: boolean }>({
    top: 0,
    left: 0,
    centered: true,
  });
  const cardRef = useRef<HTMLDivElement>(null);

  const step = STEPS[i];
  const last = i === STEPS.length - 1;

  const finish = useCallback(() => {
    setI(0);
    onClose();
  }, [onClose]);

  // Reset to the first step whenever the tour is (re)opened.
  useEffect(() => {
    if (open) setI(0);
  }, [open]);

  // Point the spotlight at the current step's element, scrolling it into view.
  useEffect(() => {
    if (!open) return;
    if (!step.sel) {
      setRect(null);
      return;
    }
    const el = document.querySelector(step.sel);
    if (!el) {
      setRect(null);
      return;
    }
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    el.scrollIntoView({ block: "center", behavior: reduce ? "auto" : "smooth" });
    const measure = () => setRect(el.getBoundingClientRect());
    measure();
    const t = window.setTimeout(measure, 280); // settle after the smooth scroll
    return () => window.clearTimeout(t);
  }, [open, i, step.sel]);

  // Keep the spotlight glued to its element as the page scrolls or resizes.
  useEffect(() => {
    if (!open || !step.sel) return;
    const track = () => {
      const el = document.querySelector(step.sel!);
      if (el) setRect(el.getBoundingClientRect());
    };
    window.addEventListener("resize", track);
    window.addEventListener("scroll", track, true);
    return () => {
      window.removeEventListener("resize", track);
      window.removeEventListener("scroll", track, true);
    };
  }, [open, i, step.sel]);

  // Place the card: below the element if it fits, otherwise above; centered
  // for the anchor-less overview steps.
  useLayoutEffect(() => {
    if (!open) return;
    const card = cardRef.current;
    const cw = card?.offsetWidth ?? 340;
    const ch = card?.offsetHeight ?? 170;
    if (!rect) {
      setPos({
        top: window.innerHeight / 2 - ch / 2,
        left: window.innerWidth / 2 - cw / 2,
        centered: true,
      });
      return;
    }
    const gap = 14;
    const fitsBelow = rect.bottom + gap + ch <= window.innerHeight - 12;
    const top = fitsBelow ? rect.bottom + gap : Math.max(12, rect.top - gap - ch);
    const left = Math.min(Math.max(12, rect.left), window.innerWidth - cw - 12);
    setPos({ top, left, centered: false });
  }, [open, rect, i]);

  // Keyboard: arrows navigate, Escape leaves.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") finish();
      else if (e.key === "ArrowRight" || e.key === "Enter") setI((n) => Math.min(STEPS.length - 1, n + 1));
      else if (e.key === "ArrowLeft") setI((n) => Math.max(0, n - 1));
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, finish]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[200]" role="dialog" aria-modal="true" aria-label="Studio tour">
      {/* Dimmer + spotlight. The giant box-shadow darkens everything except
          the highlighted element; a full dim covers the anchor-less steps. */}
      {rect ? (
        <div
          className="pointer-events-none fixed rounded-md ring-2 ring-cue transition-all duration-200"
          style={{
            top: rect.top - PAD,
            left: rect.left - PAD,
            width: rect.width + PAD * 2,
            height: rect.height + PAD * 2,
            boxShadow: "0 0 0 9999px rgba(0,0,0,0.66)",
          }}
        />
      ) : (
        <div className="fixed inset-0 bg-black/66" />
      )}

      {/* Catch clicks so the underlying studio can't be used mid-tour. */}
      <div className="fixed inset-0" onClick={() => {}} />

      {/* The step card. */}
      <div
        ref={cardRef}
        className="fixed z-[201] w-[min(340px,calc(100vw-24px))] rounded border border-cue-deep bg-panel p-4 shadow-[0_8px_24px_rgba(0,0,0,0.5)]"
        style={{ top: pos.top, left: pos.left }}
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
                onClick={() => setI((n) => Math.max(0, n - 1))}
                className="rounded border border-edge px-3 py-1.5 font-mono text-xs text-ink-2 transition-colors hover:border-edge-strong"
              >
                Back
              </button>
            )}
            <button
              onClick={() => (last ? finish() : setI((n) => n + 1))}
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

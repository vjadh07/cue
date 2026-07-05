// The lobby — Cue's welcome page. Light and airy where the studio is dark:
// same mat world, daylight side. Needs pointer interactivity (the equalizer
// ribbon), so it's a Client Component.
"use client";

import { useRef } from "react";
import Link from "next/link";

import { MAT_CLOUD } from "./mat-art";

const EQ_BARS = 56;

// Deterministic resting height per bar — a gentle skyline, same every load.
function restingScale(i: number) {
  return 0.22 + 0.14 * Math.abs(Math.sin(i * 0.9)) + 0.1 * Math.abs(Math.sin(i * 0.23));
}

// The interactive equalizer ribbon: bars rise under the cursor like a level
// meter following a fader sweep. Decorative — hidden from assistive tech.
function EqRibbon() {
  const barsRef = useRef<(HTMLSpanElement | null)[]>([]);

  function onMove(e: React.PointerEvent<HTMLDivElement>) {
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width; // 0..1 across the ribbon
    barsRef.current.forEach((bar, i) => {
      if (!bar) return;
      const center = (i + 0.5) / EQ_BARS;
      const dist = Math.abs(center - x);
      const boost = Math.exp(-(dist * dist) / 0.004); // a tight bell around the cursor
      bar.style.transform = `scaleY(${Math.min(1, restingScale(i) + boost * 0.85)})`;
    });
  }

  function onLeave() {
    barsRef.current.forEach((bar, i) => {
      if (bar) bar.style.transform = `scaleY(${restingScale(i)})`;
    });
  }

  return (
    <div
      aria-hidden="true"
      onPointerMove={onMove}
      onPointerLeave={onLeave}
      className="mx-auto flex h-16 w-full max-w-2xl items-end gap-[3px] px-2"
    >
      {Array.from({ length: EQ_BARS }).map((_, i) => (
        <span
          key={i}
          ref={(el) => {
            barsRef.current[i] = el;
          }}
          className="lobby-eq-bar h-full flex-1 origin-bottom rounded-sm bg-cue-press/70"
          style={{ transform: `scaleY(${restingScale(i)})` }}
        />
      ))}
    </div>
  );
}

// A word set as one of Cue's amber cue tags, inline in the headline.
function CueWord({ children }: { children: string }) {
  return (
    <span className="mx-1 inline-block rounded border border-cue-deep/50 bg-cue/20 px-3 align-baseline font-mono text-[0.72em] tracking-tight text-cue-press">
      [{children}]
    </span>
  );
}

const STEPS: { n: string; title: string; body: string }[] = [
  {
    n: "01",
    title: "Write",
    body: "Paste a script, or chat one into existence in the writer's room — “two old friends, one hiding something” — and shape it draft by draft.",
  },
  {
    n: "02",
    title: "Direct",
    body: "Give one note in plain English — “build from calm to furious” — and the brain marks up every line like an actor's script, beat by beat.",
  },
  {
    n: "03",
    title: "Produce",
    body: "Cast a voice per character, lay a music bed that ducks under the speech, and download the whole performance as one produced track.",
  },
];

export default function Lobby() {
  return (
    <main className="lobby relative min-h-[100dvh] overflow-hidden">
      {/* The dither clouds, printed faintly on the paper. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 hidden select-none md:block">
        <pre className="absolute -right-14 top-6 font-mono text-[11px] leading-[13px] text-ink-deep/[0.06]">
          {MAT_CLOUD}
        </pre>
        <pre className="absolute -left-20 bottom-10 rotate-180 font-mono text-[10px] leading-[12px] text-ink-deep/[0.05]">
          {MAT_CLOUD}
        </pre>
      </div>

      <div className="relative mx-auto flex min-h-[100dvh] w-full max-w-5xl flex-col px-6">
        {/* Nav */}
        <nav className="flex items-center justify-between py-6">
          <div className="flex items-center gap-2.5">
            <span className="h-2.5 w-2.5 rounded-full bg-cue shadow-[0_0_10px_1px] shadow-cue/50" />
            <span className="text-lg font-semibold tracking-tight">Cue</span>
          </div>
          <Link
            href="/studio"
            className="font-mono text-xs uppercase tracking-[0.12em] text-ink-deep-2 transition-colors duration-150 hover:text-cue-press"
          >
            Open the studio →
          </Link>
        </nav>

        {/* Hero */}
        <section className="flex flex-1 flex-col items-center justify-center pb-10 pt-14 text-center">
          <h1 className="max-w-3xl text-balance text-5xl font-semibold leading-[1.06] tracking-[-0.02em] sm:text-6xl md:text-7xl">
            You direct.
            <br />
            The voice <CueWord>performs</CueWord>.
          </h1>

          <p className="mt-7 max-w-[52ch] text-balance text-base leading-relaxed text-ink-deep-2 sm:text-lg">
            Cue turns plain-English direction into real performances — voices that
            whisper, break, and shout on your note, stitched with music into one
            produced track.
          </p>

          <div className="mt-9 flex flex-wrap items-center justify-center gap-4">
            <Link
              href="/studio"
              className="rounded border border-cue-deep bg-cue px-7 py-3.5 text-base font-semibold text-cue-ink shadow-[inset_0_1px_0_rgba(255,255,255,0.35)] transition-colors duration-150 hover:bg-cue-bright active:translate-y-px"
            >
              Try Cue →
            </Link>
            <a
              href="#how"
              className="rounded border border-ink-deep/20 px-6 py-3.5 font-mono text-xs uppercase tracking-[0.1em] text-ink-deep-2 transition-colors duration-150 hover:border-cue-deep hover:text-cue-press"
            >
              See how it works
            </a>
          </div>

          {/* The interactive level meter — sweep your cursor across it. */}
          <div className="mt-16 w-full">
            <EqRibbon />
          </div>
        </section>
      </div>

      {/* How it works */}
      <section id="how" className="relative border-t border-ink-deep/10">
        <div className="mx-auto w-full max-w-5xl px-6 py-20">
          <h2 className="text-3xl font-semibold tracking-[-0.01em]">
            Like a director talks to an actor.
          </h2>
          <p className="mt-3 max-w-[58ch] text-ink-deep-2">
            No sliders, no timeline editing. You say what you want the way you&apos;d
            say it to a person — Cue works out the rest.
          </p>

          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {STEPS.map((step) => (
              <div key={step.n} className="rounded border border-ink-deep/15 bg-paper p-6 shadow-[0_2px_0_rgba(0,0,0,0.06)]">
                <div className="flex items-baseline gap-3">
                  <span className="font-mono text-xs text-cue-press">{step.n}</span>
                  <h3 className="text-lg font-semibold">{step.title}</h3>
                </div>
                <p className="mt-3 text-sm leading-relaxed text-ink-deep-2">{step.body}</p>
              </div>
            ))}
          </div>
        </div>
      </section>

      {/* The performance: what you type vs what Cue performs. */}
      <section className="relative border-t border-ink-deep/10">
        <div className="mx-auto w-full max-w-5xl px-6 py-20">
          <div className="grid items-center gap-10 md:grid-cols-2">
            <div>
              <h2 className="text-3xl font-semibold tracking-[-0.01em]">
                Your words. Its performance.
              </h2>
              <p className="mt-4 max-w-[48ch] leading-relaxed text-ink-deep-2">
                The brain rewrites each line the way an actor marks up a script —
                cues at the exact beat where the feeling turns. Your words are never
                changed: a word-for-word validator guarantees it.
              </p>
            </div>
            <div className="flex flex-col gap-3">
              <div className="rounded border border-ink-deep/15 bg-paper p-4">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-deep-2">
                  What you type
                </span>
                <p className="mt-2 text-lg">Stop it.</p>
              </div>
              <div className="self-center font-mono text-xs text-ink-deep-2">↓ direction: “furious”</div>
              <div className="rounded border border-cue-deep/40 bg-cue/10 p-4">
                <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-cue-press">
                  What Cue performs
                </span>
                <p className="mt-2 text-lg">
                  <span className="font-mono text-sm text-cue-press">[furious]</span> STOP{" "}
                  <span className="font-mono text-sm text-cue-press">[yelling]</span> IT!
                </p>
              </div>
            </div>
          </div>
        </div>
      </section>

      {/* Footer */}
      <footer className="relative border-t border-ink-deep/10">
        <div className="mx-auto flex w-full max-w-5xl flex-wrap items-center justify-between gap-4 px-6 py-8">
          <span className="font-mono text-[10px] uppercase tracking-[0.18em] text-ink-deep-2">
            Cue · lobby · mat nº 000
          </span>
          <span className="font-mono text-[11px] text-ink-deep-2">
            Built on ElevenLabs v3 + Groq ·{" "}
            <a
              href="https://github.com/vjadh07/cue"
              className="underline decoration-ink-deep/30 underline-offset-2 transition-colors hover:text-cue-press"
            >
              open source
            </a>
          </span>
        </div>
      </footer>
    </main>
  );
}

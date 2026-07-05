// The lobby — Cue's welcome page. Light and airy where the studio is dark:
// same mat world, daylight side. The interactive layer (reactbits-inspired:
// cursor-lit grid, proximity type, scramble chip, spotlight cards, scroll
// reveals) lives in lobby-fx.tsx.
"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { MAT_CLOUD } from "./mat-art";
import {
  Aurora,
  EqRibbon,
  ProximityText,
  Reveal,
  SpotlightCard,
  TagCycler,
  useEntranceStage,
  WaveField,
} from "./lobby-fx";

// The words the headline chip cycles through — all real v3 audio tags.
const CHIP_WORDS = ["performs", "whispers", "shouts", "breaks"];

// A word set as one of Cue's amber cue tags, inline in the headline. Fixed
// width (sized to the longest word) so the headline never reflows mid-cycle.
function CueWord({ children }: { children: React.ReactNode }) {
  return (
    <span
      className="mx-1 inline-block whitespace-nowrap rounded border border-cue-deep/50 bg-cue/20 text-center align-baseline font-mono text-[0.72em] tracking-tight text-cue-press"
      style={{ width: "calc(10ch + 0.6em)" }}
    >
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

// The interactive demo: one line, four directions, each performed the way the
// real brain performs it — genuine whitelist tags, genuine stability values.
type TakeSegment = { tag?: string; word?: string };
const TAKES: { note: string; stability: string; segments: TakeSegment[] }[] = [
  {
    note: "furious",
    stability: "stability 0.10 · low = raw",
    segments: [{ tag: "furious" }, { word: "STOP" }, { tag: "yelling" }, { word: "IT!" }],
  },
  {
    note: "it's a secret",
    stability: "stability 0.35",
    segments: [{ tag: "whispers" }, { word: "Stop it…" }],
  },
  {
    note: "heartbroken",
    stability: "stability 0.20",
    segments: [{ tag: "sighs" }, { word: "Stop…" }, { tag: "voice breaking" }, { word: "it." }],
  },
  {
    note: "trying not to laugh",
    stability: "stability 0.45",
    segments: [{ tag: "laughs" }, { word: "Stop" }, { tag: "giggles" }, { word: "it!" }],
  },
];

function DirectionDemo() {
  const [active, setActive] = useState(0);
  const locked = useRef(false); // first click stops the auto-cycle
  const boxRef = useRef<HTMLDivElement>(null);
  const visible = useRef(false);

  useEffect(() => {
    const box = boxRef.current;
    if (!box) return;
    const io = new IntersectionObserver(([entry]) => (visible.current = entry.isIntersecting), {
      threshold: 0.4,
    });
    io.observe(box);
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    const cycle = setInterval(() => {
      if (!locked.current && visible.current && !reduce) {
        setActive((a) => (a + 1) % TAKES.length);
      }
    }, 3800);
    return () => {
      io.disconnect();
      clearInterval(cycle);
    };
  }, []);

  const take = TAKES[active];

  return (
    <div ref={boxRef} className="flex flex-col gap-3">
      <div className="rounded border border-ink-deep/15 bg-paper p-4">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-deep-2">
          What you type
        </span>
        <p className="mt-2 text-lg">Stop it.</p>
      </div>

      {/* The direction chips — click one and the performance changes. */}
      <div className="flex flex-wrap items-center gap-2 self-center">
        <span className="font-mono text-xs text-ink-deep-2">↓ direction:</span>
        {TAKES.map((t, i) => (
          <button
            key={t.note}
            type="button"
            aria-pressed={i === active}
            onClick={() => {
              locked.current = true;
              setActive(i);
            }}
            className={`rounded border px-2.5 py-1 font-mono text-xs transition-colors duration-150 ${
              i === active
                ? "border-cue-deep bg-cue text-cue-ink"
                : "border-ink-deep/20 text-ink-deep-2 hover:border-cue-deep hover:text-cue-press"
            }`}
          >
            “{t.note}”
          </button>
        ))}
      </div>

      <div className="rounded border border-cue-deep/40 bg-cue/10 p-4">
        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-cue-press">
          What Cue performs
        </span>
        {/* key={active} remounts the line so the segments stamp in again. */}
        <p key={active} className="mt-2 flex flex-wrap items-baseline gap-x-2 gap-y-1 text-lg">
          {take.segments.map((seg, i) =>
            seg.tag ? (
              <span
                key={i}
                className="take-tag font-mono text-sm text-cue-press"
                style={{ animationDelay: `${i * 90}ms` }}
              >
                [{seg.tag}]
              </span>
            ) : (
              <span key={i} className="take-word" style={{ animationDelay: `${i * 90}ms` }}>
                {seg.word}
              </span>
            ),
          )}
        </p>
        <p className="mt-3 border-t border-cue-deep/20 pt-2 font-mono text-[11px] text-ink-deep-2">
          {take.stability} · every word verified against your line
        </p>
      </div>
    </div>
  );
}

export default function Lobby() {
  const stage = useEntranceStage();
  const rise = (i: number) => ({
    className: `lobby-rise${stage === "set" ? " pre" : ""}`,
    style: { transitionDelay: `${i * 90}ms` },
  });

  return (
    <main className="lobby relative min-h-[100dvh] overflow-hidden">
      {/* The living backdrop: aurora wash under drifting sound-waves. */}
      <Aurora />
      <WaveField />

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
            <ProximityText text="You direct." stage={stage} baseDelay={0} />
            <br />
            <ProximityText text="The voice" stage={stage} baseDelay={280} />{" "}
            <span {...rise(6)} className={`${rise(6).className} inline-block`}>
              <CueWord>
                <TagCycler words={CHIP_WORDS} />
              </CueWord>
              .
            </span>
          </h1>

          <p
            {...rise(8)}
            className={`${rise(8).className} mt-7 max-w-[52ch] text-balance text-base leading-relaxed text-ink-deep-2 sm:text-lg`}
          >
            Cue turns plain-English direction into real performances — voices that
            whisper, break, and shout on your note, stitched with music into one
            produced track.
          </p>

          <div
            {...rise(10)}
            className={`${rise(10).className} mt-9 flex flex-wrap items-center justify-center gap-4`}
          >
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
          <div {...rise(12)} className={`${rise(12).className} mt-16 w-full`}>
            <EqRibbon />
          </div>
        </section>
      </div>

      {/* How it works */}
      <section id="how" className="relative border-t border-ink-deep/10">
        <div className="mx-auto w-full max-w-5xl px-6 py-20">
          <Reveal>
            <h2 className="text-3xl font-semibold tracking-[-0.01em]">
              Like a director talks to an actor.
            </h2>
            <p className="mt-3 max-w-[58ch] text-ink-deep-2">
              No sliders, no timeline editing. You say what you want the way you&apos;d
              say it to a person — Cue works out the rest.
            </p>
          </Reveal>

          <div className="mt-12 grid gap-6 md:grid-cols-3">
            {STEPS.map((step, i) => (
              <Reveal key={step.n} delay={i * 110}>
                <SpotlightCard className="h-full rounded border border-ink-deep/15 bg-paper p-6 shadow-[0_2px_0_rgba(0,0,0,0.06)] transition-colors duration-200 hover:border-cue-deep/50">
                  <div className="flex items-baseline gap-3">
                    <span className="font-mono text-xs text-cue-press">{step.n}</span>
                    <h3 className="text-lg font-semibold">{step.title}</h3>
                  </div>
                  <p className="mt-3 text-sm leading-relaxed text-ink-deep-2">{step.body}</p>
                </SpotlightCard>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* The performance: what you type vs what Cue performs — now playable. */}
      <section className="relative border-t border-ink-deep/10">
        <div className="mx-auto w-full max-w-5xl px-6 py-20">
          <div className="grid items-center gap-10 md:grid-cols-2">
            <Reveal>
              <h2 className="text-3xl font-semibold tracking-[-0.01em]">
                Your words. Its performance.
              </h2>
              <p className="mt-4 max-w-[48ch] leading-relaxed text-ink-deep-2">
                The brain rewrites each line the way an actor marks up a script —
                cues at the exact beat where the feeling turns. Your words are never
                changed: a word-for-word validator guarantees it.
              </p>
              <p className="mt-3 max-w-[48ch] font-mono text-xs text-ink-deep-2">
                Try a direction on the right — same line, different performance.
              </p>
            </Reveal>
            <Reveal delay={120}>
              <DirectionDemo />
            </Reveal>
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

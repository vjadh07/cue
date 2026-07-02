// The script editor needs state, click handlers, fetch, and an audio element —
// all browser-only — so this is a Client Component.
"use client";

import { useEffect, useRef, useState } from "react";

import { MAT_CLOUD } from "./mat-art";

// Where the Python backend is listening. For now this is hard-coded.
const BACKEND_URL = "http://localhost:8000";

// The voice dials the brain produces. stability/style/speed shape the
// ElevenLabs performance; volume is applied here at playback.
type Settings = { stability: number; style: number; speed: number; volume: number };

// One line after the brain has restyled it (the shape /direct returns per line).
// `speaker` is the character for a conversational line, or null for a plain
// (narrator) line.
type DirectedLine = {
  speaker: string | null;
  text: string;
  settings: Settings;
  tags: string[];
  notes: string;
  brain: string;
};

// An ElevenLabs voice the picker can offer (shape /voices returns).
type Voice = { id: string; name: string; description: string };

const SETTING_KEYS: { key: keyof Settings; label: string }[] = [
  { key: "stability", label: "STA" },
  { key: "style", label: "STY" },
  { key: "speed", label: "SPD" },
  { key: "volume", label: "VOL" },
];

const EQ_BARS = 12;

// Shared control styles — one component vocabulary across the whole surface.
const FIELD =
  "w-full rounded border border-edge bg-panel-2 px-3 py-2.5 text-[15px] leading-relaxed text-ink outline-none placeholder:text-ink-3 shadow-[inset_0_1px_2px_rgba(0,0,0,0.35)] transition-colors duration-150 focus:border-cue-deep focus:ring-1 focus:ring-cue-deep";
const BTN_PRIMARY =
  "rounded border border-cue-deep bg-cue px-5 py-2.5 text-sm font-semibold text-cue-ink shadow-[inset_0_1px_0_rgba(255,255,255,0.35)] transition-colors duration-150 hover:bg-cue-bright active:translate-y-px disabled:cursor-not-allowed disabled:opacity-40";
const BTN_QUIET =
  "rounded border border-edge-strong bg-panel-2 px-4 py-2 font-mono text-xs uppercase tracking-[0.08em] text-ink-2 transition-colors duration-150 hover:border-cue-deep hover:text-cue active:translate-y-px disabled:cursor-not-allowed disabled:opacity-50";

// A titled tool panel — boxy, hard-edged, with a 2000s-software title bar.
function Panel({
  title,
  meta,
  children,
}: {
  title: string;
  meta?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded border border-edge bg-panel shadow-[0_2px_0_rgba(0,0,0,0.25)]">
      <header className="flex items-baseline justify-between gap-3 border-b border-edge px-3 py-2">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">{title}</h2>
        {meta && <span className="font-mono text-[10px] text-ink-3">{meta}</span>}
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

// The measuring strip along the top edge of the mat. Purely decorative.
function Ruler() {
  return (
    <div aria-hidden="true" className="flex h-5 select-none overflow-hidden border-b border-edge-strong">
      {Array.from({ length: 24 }).map((_, i) => (
        <span
          key={i}
          className="flex-1 border-l border-chalk/30 pl-1 font-mono text-[9px] leading-5 text-chalk/60"
        >
          {i}
        </span>
      ))}
    </div>
  );
}

// Dither-art clouds printed faintly on the mat, behind the tools. The same art
// is reused rotated, so the two masses read as different clouds.
function MatClouds() {
  return (
    <div aria-hidden="true" className="pointer-events-none fixed inset-0 z-0 hidden select-none overflow-hidden md:block">
      <pre className="absolute -right-12 -top-8 font-mono text-[11px] leading-[13px] text-chalk/[0.06]">
        {MAT_CLOUD}
      </pre>
      <pre className="absolute -bottom-10 -left-16 rotate-180 font-mono text-[10px] leading-[12px] text-chalk/[0.045]">
        {MAT_CLOUD}
      </pre>
    </div>
  );
}

// Registration marks — the corner marks around the working area of the mat.
function CornerMarks() {
  return (
    <div aria-hidden="true" className="pointer-events-none absolute -inset-3">
      <span className="absolute left-0 top-0 h-3 w-3 border-l border-t border-chalk/40" />
      <span className="absolute right-0 top-0 h-3 w-3 border-r border-t border-chalk/40" />
      <span className="absolute bottom-0 left-0 h-3 w-3 border-b border-l border-chalk/40" />
      <span className="absolute bottom-0 right-0 h-3 w-3 border-b border-r border-chalk/40" />
    </div>
  );
}

export default function Home() {
  const [script, setScript] = useState("");
  const [direction, setDirection] = useState("");

  // The scriptwriter: a premise the brain turns into a draft script.
  const [premise, setPremise] = useState("");
  const [writing, setWriting] = useState(false);
  const [lines, setLines] = useState<DirectedLine[]>([]);
  const [directing, setDirecting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  // The actor: voices come from the backend (your ElevenLabs account), and
  // `voice` is the selected voice_id, sent to /render at playback.
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voice, setVoice] = useState("");

  // For conversational scripts: each named speaker -> a voice_id. Unlabeled
  // (narrator) lines use `voice`.
  const [cast, setCast] = useState<Record<string, string>>({});

  // Which line is mid-render (waiting on /render) and which is playing. Only one
  // line plays at a time — we reuse a single <audio> element. Index -1 means the
  // stitched full read (not an individual line).
  const [loadingLine, setLoadingLine] = useState<number | null>(null);
  const [playingLine, setPlayingLine] = useState<number | null>(null);

  // The stitched full-read track (its audio_id), once one has been made — this
  // is what the Download link points at. Cleared whenever the script or a voice
  // changes, because the track no longer matches what's on screen.
  const [readTrack, setReadTrack] = useState<string | null>(null);
  const [stitching, setStitching] = useState(false);

  const audioRef = useRef<HTMLAudioElement>(null);
  // The line we're about to play, so onPlay knows which one started without
  // depending on possibly-stale state.
  const pendingLine = useRef<number | null>(null);

  // Load the available voices once, and preselect the backend's default.
  useEffect(() => {
    fetch(`${BACKEND_URL}/voices`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: { voices: Voice[]; default: string }) => {
        setVoices(data.voices);
        setVoice(data.default);
      })
      .catch(() => {
        /* leave the picker empty; renders just use the backend default */
      });
  }, []);

  // Write: the brain drafts a script from a premise, straight into the Script
  // box — the user then directs it like any other material.
  async function handleWrite() {
    const idea = premise.trim();
    if (!idea) return;
    setErrorMessage("");
    setWriting(true);

    try {
      const response = await fetch(`${BACKEND_URL}/write`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ premise: idea }),
      });
      if (!response.ok) throw new Error(`Backend responded with ${response.status}`);
      const data: { script: string } = await response.json();
      setScript(data.script);
      // A new script invalidates the old read: clear the directed lines/track.
      setLines([]);
      setReadTrack(null);
      setPlayingLine(null);
      setLoadingLine(null);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? `Couldn't write a script: ${err.message}` : "Couldn't write a script."
      );
    } finally {
      setWriting(false);
    }
  }

  // Direct: send the whole script + one direction, get back a per-line read.
  // No audio is rendered here — that happens lazily when you press Play.
  async function handleDirect() {
    if (!script.trim()) return;
    setErrorMessage("");
    setDirecting(true);
    setLines([]);
    setPlayingLine(null);
    setLoadingLine(null);
    setReadTrack(null);

    try {
      const response = await fetch(`${BACKEND_URL}/direct`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script, direction }),
      });
      if (!response.ok) throw new Error(`Backend responded with ${response.status}`);
      const data: { lines: DirectedLine[]; speakers: string[] } = await response.json();
      setLines(data.lines);
      // Seed any newly-seen speaker with the narrator voice, so every line has a
      // valid voice; the user can then reassign each character in the Cast panel.
      setCast((prev) => {
        const next = { ...prev };
        for (const s of data.speakers) if (!next[s]) next[s] = voice;
        return next;
      });
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? `Couldn't direct the script: ${err.message}` : "Couldn't direct the script."
      );
    } finally {
      setDirecting(false);
    }
  }

  // A labeled line uses its character's voice; an unlabeled line uses the
  // narrator voice.
  function voiceFor(line: DirectedLine) {
    return line.speaker ? cast[line.speaker] ?? voice : voice;
  }

  // Play one line: render it with the settings/tags it already got from /direct,
  // then play. Reusing the same <audio> means a new Play interrupts the last.
  async function handlePlay(i: number) {
    const line = lines[i];
    const lineVoice = voiceFor(line);
    setErrorMessage("");
    pendingLine.current = i;
    setLoadingLine(i);

    try {
      const response = await fetch(`${BACKEND_URL}/render`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: line.text, settings: line.settings, tags: line.tags, voice: lineVoice }),
      });
      if (!response.ok) throw new Error(`Render failed (${response.status})`);
      const data = { audio_id: "", ext: "", ...(await response.json()) };

      const audio = audioRef.current;
      if (!audio) throw new Error("Audio player not ready.");
      audio.src = `${BACKEND_URL}/audio/${data.audio_id}.${data.ext}`;
      audio.volume = line.settings.volume;
      await audio.play(); // onPlay flips this line to "playing"
    } catch (err) {
      setLoadingLine(null);
      setErrorMessage(
        err instanceof Error ? `Couldn't play that line: ${err.message}` : "Couldn't play that line."
      );
    }
  }

  // Play the whole script as one continuous track: the backend renders every
  // line in its voice (cached lines are free) and stitches them with pauses.
  async function handleRead() {
    setErrorMessage("");
    setStitching(true);
    pendingLine.current = -1; // the full read, not an individual line

    try {
      const response = await fetch(`${BACKEND_URL}/read`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          lines: lines.map((line) => ({
            text: line.text,
            settings: line.settings,
            tags: line.tags,
            voice: voiceFor(line),
          })),
        }),
      });
      if (!response.ok) throw new Error(`Stitch failed (${response.status})`);
      const data: { audio_id: string; ext: string } = await response.json();
      setReadTrack(data.audio_id);

      const audio = audioRef.current;
      if (!audio) throw new Error("Audio player not ready.");
      audio.src = `${BACKEND_URL}/audio/${data.audio_id}.${data.ext}`;
      audio.volume = 1.0; // per-line volume is baked into the stitched track as gain
      await audio.play();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? `Couldn't play the full read: ${err.message}` : "Couldn't play the full read."
      );
    } finally {
      setStitching(false);
    }
  }

  const anyPlaying = playingLine !== null;
  const readPlaying = playingLine === -1;
  // The distinct named characters in the directed script, in first-seen order.
  const castList = Array.from(
    new Set(lines.map((l) => l.speaker).filter((s): s is string => Boolean(s)))
  );

  return (
    <main className="relative z-[1] min-h-[100dvh]">
      <MatClouds />
      {/* The mat's printed ruler, along the top edge. */}
      <Ruler />

      <div className="mx-auto w-full max-w-3xl px-6 pb-24 pt-10">
        {/* Header: the cue light means "we're live". */}
        <header className="mb-10 flex items-end justify-between gap-4">
          <div className="flex items-center gap-3">
            <span
              className={
                "h-3 w-3 rounded-full transition-colors duration-150 " +
                (anyPlaying
                  ? "bg-cue shadow-[0_0_14px_2px] shadow-cue/60"
                  : "bg-cue/30 shadow-[inset_0_0_0_1px] shadow-cue/40")
              }
            />
            <span className="text-xl font-semibold tracking-tight text-ink">Cue</span>
          </div>
          {/* Printed on the mat like the maker's brand. */}
          <span
            aria-hidden="true"
            className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-chalk/70 sm:block"
          >
            Control room · mat nº 001 · 24″ × 18″
          </span>
        </header>

        <p className="mb-8 max-w-[62ch] text-sm leading-relaxed text-chalk">
          Paste a script — one line per row — and give a single direction in plain English.
          The brain reads the whole script and performs each line for where it sits in the
          arc. Prefix a line with a name (<span className="font-mono">ALICE:</span>) to make
          it a conversation and give each character their own voice.
        </p>

        <div className="relative">
          <CornerMarks />
          <div className="flex flex-col gap-5">
            {/* The material: the script itself. */}
            <Panel title="Script" meta={lines.length > 0 ? `${lines.length} lines` : "or let the brain draft one"}>
              <textarea
                id="script"
                aria-label="Script"
                value={script}
                onChange={(e) => setScript(e.target.value)}
                rows={6}
                placeholder={"It was already too late.\nALICE: Where were you?\nBOB: ...out."}
                className={FIELD + " resize-y"}
              />
              {/* The scriptwriter: premise in, draft script out. */}
              <div className="mt-2.5 flex gap-2.5">
                <input
                  aria-label="Premise for the scriptwriter"
                  value={premise}
                  onChange={(e) => setPremise(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleWrite();
                  }}
                  placeholder="describe a scene — “two old friends, one hiding something”"
                  className={FIELD + " py-2 text-sm"}
                />
                <button
                  onClick={handleWrite}
                  disabled={writing || premise.trim() === ""}
                  className={BTN_QUIET + " shrink-0"}
                >
                  {writing ? "Writing…" : "✎ Write"}
                </button>
              </div>
            </Panel>

            {/* The direction and the narrator's voice, side by side. */}
            <div className="grid gap-5 sm:grid-cols-[1fr_240px]">
              <Panel title="Direction">
                <input
                  id="direction"
                  aria-label="Direction"
                  value={direction}
                  onChange={(e) => setDirection(e.target.value)}
                  placeholder="build from calm to furious"
                  className={FIELD}
                />
              </Panel>

              {voices.length > 0 && (
                <Panel title={castList.length > 0 ? "Narrator voice" : "Voice"}>
                  <select
                    id="voice"
                    aria-label="Voice"
                    value={voice}
                    onChange={(e) => {
                      setVoice(e.target.value);
                      setReadTrack(null); // the stitched track no longer matches
                    }}
                    className={FIELD + " cursor-pointer"}
                  >
                    {voices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.name}
                      </option>
                    ))}
                  </select>
                </Panel>
              )}
            </div>

            <div className="flex items-center gap-4">
              <button onClick={handleDirect} disabled={directing || script.trim() === ""} className={BTN_PRIMARY}>
                {directing ? "Directing…" : "Direct"}
              </button>
              {directing && (
                <span className="font-mono text-xs text-chalk/80">interpreting every line…</span>
              )}
            </div>

            {errorMessage && (
              <p
                role="alert"
                className="rounded border border-danger/50 bg-panel px-3 py-2 font-mono text-xs text-danger"
              >
                {errorMessage}
              </p>
            )}

            {/* Cast: one voice per character (only for conversational scripts). */}
            {castList.length > 0 && voices.length > 0 && (
              <Panel title="Cast" meta={`${castList.length} characters`}>
                <div className="flex flex-col gap-2.5">
                  {castList.map((speaker) => (
                    <div key={speaker} className="flex items-center gap-3">
                      <span className="w-28 shrink-0 truncate font-mono text-xs uppercase tracking-[0.1em] text-cue">
                        {speaker}
                      </span>
                      <select
                        aria-label={`Voice for ${speaker}`}
                        value={cast[speaker] ?? voice}
                        onChange={(e) => {
                          setCast((prev) => ({ ...prev, [speaker]: e.target.value }));
                          setReadTrack(null); // the stitched track no longer matches
                        }}
                        className={FIELD + " cursor-pointer py-2 text-sm"}
                      >
                        {voices.map((v) => (
                          <option key={v.id} value={v.id}>
                            {v.name}
                          </option>
                        ))}
                      </select>
                    </div>
                  ))}
                </div>
              </Panel>
            )}

            {/* The take: the whole script as one stitched track. */}
            {lines.length > 0 && (
              <Panel title="Take" meta="one track · mp3">
                <div className="flex flex-wrap items-center gap-3">
                  <button onClick={handleRead} disabled={stitching} className={BTN_PRIMARY}>
                    {stitching ? "Stitching…" : readPlaying ? "Playing…" : "▶ Play full read"}
                  </button>
                  {readTrack && (
                    <a href={`${BACKEND_URL}/audio/${readTrack}.mp3?download=1`} className={BTN_QUIET}>
                      Download
                    </a>
                  )}
                  {/* Level meter: alive only while audio is playing. */}
                  <div className="ml-auto flex h-8 items-end gap-1" aria-hidden="true">
                    {Array.from({ length: EQ_BARS }).map((_, i) => (
                      <span
                        key={i}
                        className="cue-eq-bar w-[3px] origin-bottom rounded-sm bg-cue/80"
                        style={
                          anyPlaying
                            ? {
                                height: "100%",
                                animation: `cue-eq ${0.7 + (i % 3) * 0.18}s ease-in-out ${i * 0.06}s infinite`,
                              }
                            : { height: "100%", transform: "scaleY(0.18)" }
                        }
                      />
                    ))}
                  </div>
                </div>
              </Panel>
            )}

            {/* The directed script: one strip per line, laid out on the mat. */}
            {lines.length > 0 && (
              <div className="flex flex-col gap-3">
                {lines.map((line, i) => {
                  const isLoading = loadingLine === i;
                  const isPlaying = playingLine === i;
                  return (
                    <article
                      key={i}
                      className={
                        "rounded border bg-panel shadow-[0_2px_0_rgba(0,0,0,0.25)] transition-colors duration-150 " +
                        (isPlaying ? "border-cue-deep" : "border-edge")
                      }
                    >
                      <header className="flex items-baseline justify-between gap-3 border-b border-edge px-3 py-1.5">
                        <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
                          L{String(i + 1).padStart(2, "0")}
                          {line.speaker && <span className="text-cue"> · {line.speaker}</span>}
                        </span>
                        {line.notes && (
                          <span className="truncate font-mono text-[10px] text-ink-3">read as: {line.notes}</span>
                        )}
                      </header>

                      <div className="flex items-start justify-between gap-4 p-3">
                        <div className="min-w-0 flex-col gap-2">
                          <p className="text-[15px] leading-relaxed text-ink">{line.text}</p>
                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                            {line.tags.map((tag) => (
                              <span
                                key={tag}
                                className="rounded-sm border border-cue-deep/60 bg-cue/10 px-1.5 py-0.5 font-mono text-[10px] text-cue"
                              >
                                [{tag}]
                              </span>
                            ))}
                            <span className="font-mono text-[10px] text-ink-3">
                              {SETTING_KEYS.map(({ key, label }) => `${label} ${line.settings[key].toFixed(2)}`).join(
                                "  ·  "
                              )}
                              {"  ·  "}
                              {line.brain}
                            </span>
                          </div>
                        </div>
                        <button onClick={() => handlePlay(i)} disabled={isLoading} className={BTN_QUIET + " shrink-0"}>
                          {isLoading ? "Rendering…" : isPlaying ? "Playing…" : "Play"}
                        </button>
                      </div>
                    </article>
                  );
                })}
              </div>
            )}
          </div>
        </div>

        {/* One shared audio player; events drive the per-line play state. */}
        <audio
          ref={audioRef}
          className="hidden"
          onPlay={() => {
            setPlayingLine(pendingLine.current);
            setLoadingLine(null);
          }}
          onEnded={() => setPlayingLine(null)}
          onError={() => {
            setLoadingLine(null);
            setPlayingLine(null);
            setErrorMessage("Something went wrong while playing the audio.");
          }}
        />
      </div>
    </main>
  );
}

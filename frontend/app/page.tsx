// The script editor needs state, click handlers, fetch, and an audio element —
// all browser-only — so this is a Client Component.
"use client";

import { useEffect, useRef, useState } from "react";

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

export default function Home() {
  const [script, setScript] = useState("");
  const [direction, setDirection] = useState("");
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
    <main className="min-h-[100dvh] flex justify-center px-6 py-16">
      <div className="w-full max-w-2xl flex flex-col gap-7">
        {/* Header: a cue light that glows while a line is playing. */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span
              className={
                "h-2.5 w-2.5 rounded-full transition " +
                (anyPlaying
                  ? "bg-amber-400 shadow-[0_0_12px_2px] shadow-amber-400/60"
                  : "bg-amber-400/30")
              }
            />
            <span className="text-lg font-semibold tracking-tight">Cue</span>
          </div>
          <span className="font-mono text-[11px] uppercase tracking-[0.2em] text-zinc-500">
            control room
          </span>
        </header>

        <p className="text-sm leading-relaxed text-zinc-400">
          Paste a script — one line per row — then give a single direction in plain
          English. The brain reads the whole script and performs each line for where
          it sits in the arc. Prefix a line with a name (<span className="font-mono text-zinc-300">ALICE:</span>)
          to make it a conversation and give each character their own voice.
        </p>

        {/* Voice picker — the actor for the whole read. */}
        {voices.length > 0 && (
          <div className="flex flex-col gap-2">
            <label htmlFor="voice" className="font-mono text-[11px] uppercase tracking-[0.15em] text-zinc-400">
              {castList.length > 0 ? "Narrator voice" : "Voice"}
            </label>
            <select
              id="voice"
              value={voice}
              onChange={(e) => {
                setVoice(e.target.value);
                setReadTrack(null); // the stitched track no longer matches
              }}
              className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-4 py-3 text-base text-zinc-100 outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-400/30"
            >
              {voices.map((v) => (
                <option key={v.id} value={v.id}>
                  {v.name}
                </option>
              ))}
            </select>
          </div>
        )}

        {/* Script input */}
        <div className="flex flex-col gap-2">
          <label htmlFor="script" className="font-mono text-[11px] uppercase tracking-[0.15em] text-zinc-400">
            Script
          </label>
          <textarea
            id="script"
            value={script}
            onChange={(e) => setScript(e.target.value)}
            rows={5}
            placeholder={"We actually did it.\nAfter all this time.\nI can't believe it."}
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-4 py-3 text-base leading-relaxed text-zinc-100 outline-none resize-y placeholder:text-zinc-600 focus:border-amber-400 focus:ring-2 focus:ring-amber-400/30"
          />
        </div>

        {/* Direction input */}
        <div className="flex flex-col gap-2">
          <label htmlFor="direction" className="font-mono text-[11px] uppercase tracking-[0.15em] text-zinc-400">
            Direction
          </label>
          <input
            id="direction"
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
            placeholder="build from calm to furious"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-4 py-3 text-base text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-amber-400 focus:ring-2 focus:ring-amber-400/30"
          />
        </div>

        <button
          onClick={handleDirect}
          disabled={directing || script.trim() === ""}
          className="self-start rounded-lg bg-amber-400 px-6 py-3 text-base font-semibold text-zinc-950 transition active:translate-y-px hover:bg-amber-300 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {directing ? "Directing…" : "Direct"}
        </button>

        {errorMessage && (
          <p className="text-sm text-red-400" role="alert">
            {errorMessage}
          </p>
        )}

        {/* Cast: one voice per character (only for conversational scripts). */}
        {castList.length > 0 && voices.length > 0 && (
          <div className="flex flex-col gap-3 border-t border-zinc-800 pt-5">
            <span className="font-mono text-[11px] uppercase tracking-[0.15em] text-zinc-400">
              Cast
            </span>
            {castList.map((speaker) => (
              <div key={speaker} className="flex items-center gap-3">
                <span className="w-24 shrink-0 truncate font-mono text-xs uppercase tracking-[0.1em] text-amber-300/90">
                  {speaker}
                </span>
                <select
                  value={cast[speaker] ?? voice}
                  onChange={(e) => {
                    setCast((prev) => ({ ...prev, [speaker]: e.target.value }));
                    setReadTrack(null); // the stitched track no longer matches
                  }}
                  className="flex-1 rounded-lg border border-zinc-700 bg-zinc-950/60 px-3 py-2 text-sm text-zinc-100 outline-none focus:border-amber-400 focus:ring-2 focus:ring-amber-400/30"
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
        )}

        {/* The full read: play the whole script as one stitched track. */}
        {lines.length > 0 && (
          <div className="flex items-center gap-3 border-t border-zinc-800 pt-5">
            <button
              onClick={handleRead}
              disabled={stitching}
              className="rounded-lg bg-amber-400 px-5 py-2.5 text-sm font-semibold text-zinc-950 transition active:translate-y-px hover:bg-amber-300 disabled:opacity-40 disabled:cursor-not-allowed"
            >
              {stitching ? "Stitching…" : readPlaying ? "Playing…" : "▶ Play full read"}
            </button>
            {readTrack && (
              <a
                href={`${BACKEND_URL}/audio/${readTrack}.mp3?download=1`}
                className="rounded-lg border border-zinc-700 px-5 py-2.5 text-sm font-semibold text-zinc-300 transition hover:border-amber-400/60 hover:text-amber-300"
              >
                Download
              </a>
            )}
          </div>
        )}

        {/* The directed script: a card per line. */}
        {lines.length > 0 && (
          <div className="flex flex-col gap-3 border-t border-zinc-800 pt-5">
            {lines.map((line, i) => {
              const isLoading = loadingLine === i;
              const isPlaying = playingLine === i;
              return (
                <div
                  key={i}
                  className={
                    "rounded-lg border bg-zinc-900/40 p-4 flex flex-col gap-3 transition " +
                    (isPlaying ? "border-amber-400/60" : "border-zinc-800")
                  }
                >
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex flex-col gap-1">
                      {line.speaker && (
                        <span className="font-mono text-[11px] uppercase tracking-[0.1em] text-amber-300/70">
                          {line.speaker}
                        </span>
                      )}
                      <p className="text-base leading-relaxed text-zinc-100">{line.text}</p>
                    </div>
                    <button
                      onClick={() => handlePlay(i)}
                      disabled={isLoading}
                      className="shrink-0 rounded-md border border-amber-400/40 bg-amber-400/10 px-3 py-1.5 font-mono text-xs uppercase tracking-[0.1em] text-amber-300 transition active:translate-y-px hover:bg-amber-400/20 disabled:opacity-50"
                    >
                      {isLoading ? "Rendering…" : isPlaying ? "Playing…" : "Play"}
                    </button>
                  </div>

                  {line.tags.length > 0 && (
                    <div className="flex flex-wrap gap-1.5">
                      {line.tags.map((tag) => (
                        <span
                          key={tag}
                          className="rounded-md border border-amber-400/30 bg-amber-400/10 px-2 py-0.5 font-mono text-[11px] text-amber-300/90"
                        >
                          [{tag}]
                        </span>
                      ))}
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-x-3 gap-y-1 font-mono text-[11px] text-zinc-500">
                    {SETTING_KEYS.map(({ key, label }) => (
                      <span key={key}>
                        {label} <span className="text-zinc-300 tabular-nums">{line.settings[key].toFixed(2)}</span>
                      </span>
                    ))}
                    <span className="text-zinc-600">· {line.brain}</span>
                  </div>

                  {line.notes && (
                    <p className="font-mono text-xs text-amber-300/80">read as: {line.notes}</p>
                  )}
                </div>
              );
            })}
          </div>
        )}

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

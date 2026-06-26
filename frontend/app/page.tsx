// This page needs state, a click handler, fetch, and an audio element — all
// browser-only things — so it must be a Client Component.
"use client";

import { useRef, useState } from "react";

// Where the Python backend is listening. For now this is hard-coded.
const BACKEND_URL = "http://localhost:8000";

// What the screen can be doing at any moment. "connecting" covers the backend
// interpreting + rendering, so we label it "Rendering…".
type Status = "idle" | "connecting" | "speaking" | "error";

// The voice dials the brain produces. stability/style/speed shape the
// ElevenLabs performance; volume is applied here at playback.
type Settings = { stability: number; style: number; speed: number; volume: number };

const NEUTRAL: Settings = { stability: 0.5, style: 0.3, speed: 1.0, volume: 1.0 };

const METERS: { key: keyof Settings; label: string; min: number; max: number }[] = [
  { key: "stability", label: "STA", min: 0, max: 1 },
  { key: "style", label: "STY", min: 0, max: 1 },
  { key: "speed", label: "SPD", min: 0.7, max: 1.2 },
  { key: "volume", label: "VOL", min: 0.1, max: 1.0 },
];

const EQ_BARS = 9;

type SpeakResponse = {
  audio_id: string;
  ext: string;
  engine: string;
  cached: boolean;
  settings: Settings;
  notes: string;
  brain: string;
};

export default function Home() {
  const [line, setLine] = useState("");
  const [direction, setDirection] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [settings, setSettings] = useState<Settings>(NEUTRAL);
  const [notes, setNotes] = useState("");
  const [engine, setEngine] = useState("");
  const [brain, setBrain] = useState("");
  const [cached, setCached] = useState(false);

  const audioRef = useRef<HTMLAudioElement>(null);

  async function handlePlay() {
    const text = line.trim();
    if (!text) return;

    setErrorMessage("");
    setStatus("connecting");

    try {
      // 1. Ask the backend to interpret the direction and render the line.
      const response = await fetch(`${BACKEND_URL}/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, direction }),
      });

      if (!response.ok) {
        throw new Error(`Backend responded with ${response.status}`);
      }

      const data: SpeakResponse = await response.json();
      setSettings(data.settings);
      setNotes(data.notes);
      setEngine(data.engine);
      setBrain(data.brain);
      setCached(data.cached);

      // 2. Play the rendered file; apply volume here at playback.
      const audio = audioRef.current;
      if (!audio) throw new Error("Audio player not ready.");
      audio.src = `${BACKEND_URL}/audio/${data.audio_id}.${data.ext}`;
      audio.volume = data.settings.volume;
      await audio.play(); // onPlay flips status to "speaking"
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? `Couldn't render the line: ${err.message}`
          : "Couldn't render the line."
      );
      setStatus("error");
    }
  }

  const isBusy = status === "connecting" || status === "speaking";
  const speaking = status === "speaking";

  const buttonLabel =
    status === "connecting"
      ? "Rendering…"
      : speaking
        ? "Speaking…"
        : "Play";

  return (
    <main className="min-h-[100dvh] flex items-center justify-center px-6 py-16">
      <div className="w-full max-w-lg rounded-xl border border-zinc-800 bg-zinc-900/40 p-6 sm:p-8 flex flex-col gap-7">
        {/* Header: a cue light that glows while speaking, plus the room label. */}
        <header className="flex items-center justify-between">
          <div className="flex items-center gap-2.5">
            <span
              className={
                "h-2.5 w-2.5 rounded-full transition " +
                (speaking
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
          Type a line, then direct it in plain English. The brain reads your
          direction and the voice performs it.
        </p>

        {/* Line input */}
        <div className="flex flex-col gap-2">
          <label
            htmlFor="line"
            className="font-mono text-[11px] uppercase tracking-[0.15em] text-zinc-400"
          >
            Line
          </label>
          <textarea
            id="line"
            value={line}
            onChange={(e) => setLine(e.target.value)}
            rows={2}
            placeholder="We actually did it."
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-4 py-3 text-base leading-relaxed text-zinc-100 outline-none resize-y placeholder:text-zinc-600 focus:border-amber-400 focus:ring-2 focus:ring-amber-400/30"
          />
        </div>

        {/* Direction input */}
        <div className="flex flex-col gap-2">
          <label
            htmlFor="direction"
            className="font-mono text-[11px] uppercase tracking-[0.15em] text-zinc-400"
          >
            Direction
          </label>
          <input
            id="direction"
            value={direction}
            onChange={(e) => setDirection(e.target.value)}
            placeholder="exhausted and resigned, almost a whisper"
            className="w-full rounded-lg border border-zinc-700 bg-zinc-950/60 px-4 py-3 text-base text-zinc-100 outline-none placeholder:text-zinc-600 focus:border-amber-400 focus:ring-2 focus:ring-amber-400/30"
          />
        </div>

        <button
          onClick={handlePlay}
          disabled={isBusy || line.trim() === ""}
          className="self-start rounded-lg bg-amber-400 px-6 py-3 text-base font-semibold text-zinc-950 transition active:translate-y-px hover:bg-amber-300 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {buttonLabel}
        </button>

        {/* Equalizer: animates only while speaking. */}
        <div className="flex items-end gap-1.5 h-10" aria-hidden="true">
          {Array.from({ length: EQ_BARS }).map((_, i) => (
            <span
              key={i}
              className="cue-eq-bar h-full flex-1 max-w-[7px] origin-bottom rounded-full bg-amber-400/70"
              style={
                speaking
                  ? {
                      animation: `cue-eq ${0.7 + (i % 3) * 0.18}s ease-in-out ${
                        i * 0.07
                      }s infinite`,
                    }
                  : { transform: "scaleY(0.18)" }
              }
            />
          ))}
        </div>

        {/* Meters + engine/brain readout, console-style. */}
        <div className="flex flex-col gap-3 border-t border-zinc-800 pt-5">
          {METERS.map(({ key, label, min, max }) => {
            const value = settings[key];
            const fill = Math.round(((value - min) / (max - min)) * 100);
            return (
              <div key={key} className="flex items-center gap-3">
                <span className="font-mono text-[11px] uppercase tracking-[0.15em] text-zinc-500 w-8">
                  {label}
                </span>
                <div className="flex-1 h-1.5 rounded-full bg-zinc-800 overflow-hidden">
                  <div
                    className="h-full rounded-full bg-amber-400/80 transition-[width]"
                    style={{ width: `${Math.min(100, Math.max(0, fill))}%` }}
                  />
                </div>
                <span className="font-mono text-sm text-zinc-200 w-12 text-right tabular-nums">
                  {value.toFixed(2)}
                </span>
              </div>
            );
          })}

          <p className="font-mono text-xs text-zinc-500">
            engine: <span className="text-amber-300/90">{engine || "ready"}</span>
            {brain && (
              <>
                {" · "}brain: <span className="text-amber-300/90">{brain}</span>
              </>
            )}
            {cached && <span> · cached</span>}
          </p>

          {notes ? (
            <p className="font-mono text-xs text-amber-300/90">read as: {notes}</p>
          ) : (
            <p className="font-mono text-xs text-zinc-600">
              no direction, reading neutrally
            </p>
          )}
        </div>

        {status === "error" && (
          <p className="text-sm text-red-400" role="alert">
            {errorMessage}
          </p>
        )}

        {/* The actual audio player, hidden. Events drive the status/equalizer. */}
        <audio
          ref={audioRef}
          className="hidden"
          onPlay={() => setStatus("speaking")}
          onEnded={() => setStatus("idle")}
          onError={() => {
            setErrorMessage("Something went wrong while playing the audio.");
            setStatus("error");
          }}
        />
      </div>
    </main>
  );
}

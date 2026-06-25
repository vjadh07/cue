// This page needs state, a click handler, fetch, and the browser's speech
// API — all browser-only things — so it must be a Client Component.
"use client";

import { useState } from "react";

// Where the Python backend is listening. For Step 2 this is hard-coded; later
// we can move it to an environment variable.
const BACKEND_URL = "http://localhost:8000";

// What the screen can be doing at any moment.
type Status = "idle" | "connecting" | "speaking" | "error";

// The voice knobs the backend returns, with the safe ranges it clamps to.
// We use the ranges to draw each meter's fill.
type Settings = { speed: number; pitch: number; volume: number };

const NEUTRAL: Settings = { speed: 1.0, pitch: 1.0, volume: 1.0 };

const METERS: { key: keyof Settings; label: string; min: number; max: number }[] = [
  { key: "speed", label: "SPD", min: 0.5, max: 2.0 },
  { key: "pitch", label: "PIT", min: 0.5, max: 1.8 },
  { key: "volume", label: "VOL", min: 0.1, max: 1.0 },
];

const EQ_BARS = 9;

export default function Home() {
  const [line, setLine] = useState("");
  const [direction, setDirection] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");
  const [settings, setSettings] = useState<Settings>(NEUTRAL);
  const [matched, setMatched] = useState<string[]>([]);

  async function handlePlay() {
    const text = line.trim();
    if (!text) return;

    setErrorMessage("");
    setStatus("connecting");

    try {
      // 1. Send the line + direction to the backend; it returns the voice
      //    settings it worked out and the words it matched.
      const response = await fetch(`${BACKEND_URL}/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, direction }),
      });

      if (!response.ok) {
        throw new Error(`Backend responded with ${response.status}`);
      }

      const data: { received: string; settings: Settings; matched: string[] } =
        await response.json();

      setSettings(data.settings);
      setMatched(data.matched);

      // 2. Make sure the browser actually has a built-in voice.
      if (typeof window === "undefined" || !window.speechSynthesis) {
        throw new Error("This browser has no built-in speech voice.");
      }

      // 3. Apply the settings to the browser voice and speak.
      const utterance = new SpeechSynthesisUtterance(data.received);
      utterance.rate = data.settings.speed;
      utterance.pitch = data.settings.pitch;
      utterance.volume = data.settings.volume;
      utterance.onend = () => setStatus("idle");
      utterance.onerror = () => {
        setErrorMessage("Something went wrong while speaking.");
        setStatus("error");
      };

      setStatus("speaking");
      window.speechSynthesis.cancel(); // stop anything already talking
      window.speechSynthesis.speak(utterance);
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? `Couldn't reach the backend: ${err.message}`
          : "Couldn't reach the backend."
      );
      setStatus("error");
    }
  }

  const isBusy = status === "connecting" || status === "speaking";
  const speaking = status === "speaking";

  const buttonLabel =
    status === "connecting"
      ? "Connecting…"
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
          Type a line, add a direction in plain English, and hear it. The
          direction sets the voice; matched words show what it understood.
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
            placeholder="Welcome to Cue."
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
            placeholder="warm and slow"
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

        {/* Meters: the resulting voice settings, console-style. */}
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

          {matched.length > 0 ? (
            <p className="font-mono text-xs text-amber-300/90">
              matched: {matched.join(" · ")}
            </p>
          ) : (
            <p className="font-mono text-xs text-zinc-600">
              no direction words recognized, reading neutrally
            </p>
          )}
        </div>

        {status === "error" && (
          <p className="text-sm text-red-400" role="alert">
            {errorMessage}
          </p>
        )}
      </div>
    </main>
  );
}

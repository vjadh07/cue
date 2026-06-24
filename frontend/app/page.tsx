// This page needs state, a click handler, fetch, and the browser's speech
// API — all browser-only things — so it must be a Client Component.
"use client";

import { useState } from "react";

// Where the Python backend is listening. For Step 1 this is hard-coded; later
// we can move it to an environment variable.
const BACKEND_URL = "http://localhost:8000";

// The four things the screen can be doing at any moment. Tracking this lets us
// show the right label and message instead of only the happy path.
type Status = "idle" | "connecting" | "speaking" | "error";

export default function Home() {
  const [line, setLine] = useState("");
  const [status, setStatus] = useState<Status>("idle");
  const [errorMessage, setErrorMessage] = useState("");

  async function handlePlay() {
    const text = line.trim();
    if (!text) return;

    setErrorMessage("");
    setStatus("connecting");

    try {
      // 1. Send the line to the backend and wait for its confirmation.
      //    This is the round trip that proves the frontend-to-backend pipe works.
      const response = await fetch(`${BACKEND_URL}/speak`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });

      if (!response.ok) {
        throw new Error(`Backend responded with ${response.status}`);
      }

      const data: { received: string } = await response.json();

      // 2. Make sure the browser actually has a built-in voice.
      if (typeof window === "undefined" || !window.speechSynthesis) {
        throw new Error("This browser has no built-in speech voice.");
      }

      // 3. Hand the confirmed text to the browser's voice and speak it.
      const utterance = new SpeechSynthesisUtterance(data.received);
      utterance.onend = () => setStatus("idle");
      utterance.onerror = () => {
        setErrorMessage("Something went wrong while speaking.");
        setStatus("error");
      };

      setStatus("speaking");
      window.speechSynthesis.cancel(); // stop anything already talking
      window.speechSynthesis.speak(utterance);
    } catch (err) {
      // Most likely the backend isn't running. Say so plainly.
      setErrorMessage(
        err instanceof Error
          ? `Couldn't reach the backend: ${err.message}`
          : "Couldn't reach the backend."
      );
      setStatus("error");
    }
  }

  const isBusy = status === "connecting" || status === "speaking";

  const buttonLabel =
    status === "connecting"
      ? "Connecting…"
      : status === "speaking"
        ? "Speaking…"
        : "Play";

  return (
    <main className="min-h-[100dvh] flex items-center justify-center px-6 py-16">
      <div className="w-full max-w-xl flex flex-col gap-8">
        <header className="flex flex-col gap-2">
          <h1 className="text-3xl font-semibold tracking-tight">Cue</h1>
          <p className="text-base text-zinc-500 dark:text-zinc-400 leading-relaxed">
            Type a line and hear it read aloud. This is the bare plumbing: the
            line goes to the backend, comes back, and your browser speaks it.
          </p>
        </header>

        <div className="flex flex-col gap-2">
          <label htmlFor="line" className="text-sm font-medium">
            Your line
          </label>
          <textarea
            id="line"
            value={line}
            onChange={(e) => setLine(e.target.value)}
            rows={3}
            placeholder="Welcome to Cue."
            className="w-full rounded-lg border border-zinc-300 dark:border-zinc-700 bg-transparent px-4 py-3 text-base leading-relaxed outline-none resize-y placeholder:text-zinc-400 dark:placeholder:text-zinc-500 focus:border-amber-400 focus:ring-2 focus:ring-amber-400/40"
          />
        </div>

        <button
          onClick={handlePlay}
          disabled={isBusy || line.trim() === ""}
          className="self-start rounded-lg bg-amber-400 px-6 py-3 text-base font-semibold text-zinc-950 transition active:translate-y-px hover:bg-amber-300 disabled:opacity-40 disabled:cursor-not-allowed"
        >
          {buttonLabel}
        </button>

        {status === "error" && (
          <p className="text-sm text-red-600 dark:text-red-400" role="alert">
            {errorMessage}
          </p>
        )}
      </div>
    </main>
  );
}

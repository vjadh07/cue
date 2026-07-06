// The script editor needs state, click handlers, fetch, and an audio element —
// all browser-only — so this is a Client Component.
"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { MAT_CLOUD } from "../mat-art";

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
  // The performed rewrite: the same words with inline [tags] and expressive
  // punctuation, or null when the brain didn't produce a valid one.
  delivery: string | null;
  brain: string;
};

// An ElevenLabs voice the picker can offer (shape /voices returns).
type Voice = { id: string; name: string; description: string };

// One turn of the writer's-room chat. Assistant turns may carry a script draft.
type ChatTurn = { role: "user" | "assistant"; text: string; script?: string | null };

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
      <pre className="absolute -right-12 -top-8 font-mono text-[11px] leading-[13px] text-chalk/[0.1]">
        {MAT_CLOUD}
      </pre>
      <pre className="absolute -bottom-10 -left-16 rotate-180 font-mono text-[10px] leading-[12px] text-chalk/[0.07]">
        {MAT_CLOUD}
      </pre>
    </div>
  );
}

// Render a delivery string with its inline [tags] highlighted like cue marks.
function Performance({ delivery }: { delivery: string }) {
  return (
    <>
      {delivery.split(/(\[[^\]]+\])/).map((part, i) =>
        part.startsWith("[") ? (
          <span key={i} className="font-mono text-[0.8em] text-cue">
            {part}
          </span>
        ) : (
          <span key={i}>{part}</span>
        )
      )}
    </>
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

  // The writer's room: a running chat with the brain. Each assistant turn may
  // carry a script draft; nothing touches the Script box until "Use as script".
  const [chatLog, setChatLog] = useState<ChatTurn[]>([]);
  const [chatInput, setChatInput] = useState("");
  const [chatting, setChatting] = useState(false);
  const [lines, setLines] = useState<DirectedLine[]>([]);
  const [directing, setDirecting] = useState(false);
  const [errorMessage, setErrorMessage] = useState("");

  // The actor: voices come from the backend (your ElevenLabs account), and
  // `voice` is the selected voice_id, sent to /render at playback.
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voice, setVoice] = useState("");

  // Bring-your-own-key: a visitor's ElevenLabs key. Lives only in this
  // browser (its own storage entry, never in the workbench blob) and rides
  // each render/read as a header, so their reads spend their credits.
  const [elKey, setElKey] = useState("");
  const [keyPanelOpen, setKeyPanelOpen] = useState(false);
  const [keyInput, setKeyInput] = useState("");
  const [keyStatus, setKeyStatus] = useState<"none" | "checking" | "ok" | "bad">("none");
  // Session-only by default: the key dies with the tab unless the visitor
  // explicitly asks this device to remember it.
  const [rememberKey, setRememberKey] = useState(false);

  // For conversational scripts: each named speaker -> a voice_id. Unlabeled
  // (narrator) lines use `voice`.
  const [cast, setCast] = useState<Record<string, string>>({});

  // The music bed under the full read ("" = none), from GET /music.
  const [musicTracks, setMusicTracks] = useState<{ id: string; name: string }[]>([]);
  const [music, setMusic] = useState("");

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
  // Don't write the workbench to storage until we've restored it — otherwise
  // the first (empty) render would clobber the saved session.
  const hydrated = useRef(false);
  const threadRef = useRef<HTMLDivElement>(null);

  // Keep the newest chat turn in view.
  useEffect(() => {
    threadRef.current?.scrollTo({ top: threadRef.current.scrollHeight });
  }, [chatLog, chatting]);

  // Restore the workbench: a refresh shouldn't lose your script, direction,
  // chat thread, or cast. (Directed lines re-Direct cheaply, so they're not kept.)
  useEffect(() => {
    try {
      const saved = localStorage.getItem("cue-workbench");
      if (saved) {
        const data = JSON.parse(saved);
        if (typeof data.script === "string") setScript(data.script);
        if (typeof data.direction === "string") setDirection(data.direction);
        if (typeof data.voice === "string") setVoice(data.voice);
        if (typeof data.music === "string") setMusic(data.music);
        if (Array.isArray(data.chatLog)) setChatLog(data.chatLog);
        if (data.cast && typeof data.cast === "object") setCast(data.cast);
      }
    } catch {
      /* corrupt storage — start fresh */
    }
    try {
      const remembered = localStorage.getItem("cue-elevenlabs-key");
      const sessionOnly = sessionStorage.getItem("cue-elevenlabs-key");
      if (remembered) {
        setElKey(remembered);
        setRememberKey(true);
      } else if (sessionOnly) {
        setElKey(sessionOnly);
      }
    } catch {
      /* best-effort */
    }
    hydrated.current = true;
  }, []);

  // Save the workbench (debounced, so typing doesn't hammer storage).
  useEffect(() => {
    if (!hydrated.current) return;
    const timer = setTimeout(() => {
      try {
        localStorage.setItem(
          "cue-workbench",
          JSON.stringify({ script, direction, voice, music, chatLog, cast })
        );
      } catch {
        /* storage full or blocked — persistence is best-effort */
      }
    }, 300);
    return () => clearTimeout(timer);
  }, [script, direction, voice, music, chatLog, cast]);

  // Load the music beds once.
  useEffect(() => {
    fetch(`${BACKEND_URL}/music`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((data: { tracks: { id: string; name: string }[] }) => setMusicTracks(data.tracks))
      .catch(() => {
        /* no picker; reads just play without music */
      });
  }, []);

  // Load the available voices. With a visitor key the list is THEIR account's
  // voices (clones included); if their stored key has gone stale we mark it
  // and reload the host list so the picker never sits empty. Keep a restored
  // voice if it still exists; otherwise fall back to the backend's default.
  useEffect(() => {
    const load = (headers?: Record<string, string>) =>
      fetch(`${BACKEND_URL}/voices`, headers ? { headers } : undefined)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
        .then((data: { voices: Voice[]; default: string }) => {
          setVoices(data.voices);
          setVoice((prev) => (prev && data.voices.some((v) => v.id === prev) ? prev : data.default));
        });

    if (elKey) {
      load({ "X-ElevenLabs-Key": elKey })
        .then(() => setKeyStatus("ok"))
        .catch(() => {
          setKeyStatus("bad");
          load().catch(() => {
            /* leave the picker empty; renders just use the backend default */
          });
        });
    } else {
      load().catch(() => {
        /* leave the picker empty; renders just use the backend default */
      });
    }
  }, [elKey]);

  // The header every credit-spending call carries when a visitor key is set.
  const keyHeader: Record<string, string> = elKey ? { "X-ElevenLabs-Key": elKey } : {};

  // Verify a pasted key against /voices before trusting it, then keep it in
  // this browser only. Removing it goes back to the studio's own credits.
  async function handleSaveKey() {
    const candidate = keyInput.trim();
    if (!candidate) return;
    setKeyStatus("checking");
    try {
      const response = await fetch(`${BACKEND_URL}/voices`, {
        headers: { "X-ElevenLabs-Key": candidate },
      });
      if (!response.ok) throw new Error(String(response.status));
      setElKey(candidate); // triggers the voices reload with the new key
      setKeyInput("");
      setKeyStatus("ok");
      try {
        // Exactly one home for the key: this tab, or this device on request.
        if (rememberKey) {
          localStorage.setItem("cue-elevenlabs-key", candidate);
          sessionStorage.removeItem("cue-elevenlabs-key");
        } else {
          sessionStorage.setItem("cue-elevenlabs-key", candidate);
          localStorage.removeItem("cue-elevenlabs-key");
        }
      } catch {
        /* best-effort */
      }
    } catch {
      setKeyStatus("bad");
    }
  }

  function handleRemoveKey() {
    setElKey("");
    setKeyInput("");
    setKeyStatus("none");
    setRememberKey(false);
    try {
      localStorage.removeItem("cue-elevenlabs-key");
      sessionStorage.removeItem("cue-elevenlabs-key");
    } catch {
      /* best-effort */
    }
  }

  // One writer's-room turn: send the whole thread so "make it shorter" revises
  // the brain's own last draft. The reply may carry a new draft.
  async function handleChat() {
    const said = chatInput.trim();
    if (!said || chatting) return;
    setErrorMessage("");
    setChatting(true);
    setChatInput("");
    const log = [...chatLog, { role: "user" as const, text: said }];
    setChatLog(log);

    try {
      const response = await fetch(`${BACKEND_URL}/chat`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          // Assistant history includes its drafts, so the brain can revise them.
          messages: log.map((t) => ({
            role: t.role,
            content: t.script ? `${t.text}\n\n${t.script}` : t.text,
          })),
        }),
      });
      if (!response.ok) throw new Error(`Backend responded with ${response.status}`);
      const data: { message: string; script: string | null } = await response.json();
      setChatLog((prev) => [...prev, { role: "assistant", text: data.message, script: data.script }]);
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? `The writer's room is down: ${err.message}` : "The writer's room is down."
      );
    } finally {
      setChatting(false);
    }
  }

  // Start a fresh session: wipe the whole workbench, including saved storage.
  function handleClearMat() {
    if (!window.confirm("Clear the mat? Script, chat, and cast will be wiped.")) return;
    setScript("");
    setDirection("");
    setChatLog([]);
    setChatInput("");
    setLines([]);
    setCast({});
    setMusic("");
    setReadTrack(null);
    setPlayingLine(null);
    setLoadingLine(null);
    setErrorMessage("");
    try {
      localStorage.removeItem("cue-workbench");
    } catch {
      /* best-effort */
    }
  }

  // Move a draft from the writer's room into production.
  function useDraft(draft: string) {
    setScript(draft);
    // A new script invalidates the old read: clear the directed lines/track.
    setLines([]);
    setReadTrack(null);
    setPlayingLine(null);
    setLoadingLine(null);
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
        headers: { "Content-Type": "application/json", ...keyHeader },
        body: JSON.stringify({
          text: line.text,
          settings: line.settings,
          tags: line.tags,
          voice: lineVoice,
          delivery: line.delivery ?? "",
        }),
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
        headers: { "Content-Type": "application/json", ...keyHeader },
        body: JSON.stringify({
          lines: lines.map((line) => ({
            text: line.text,
            settings: line.settings,
            tags: line.tags,
            voice: voiceFor(line),
            delivery: line.delivery ?? "",
          })),
          music,
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

      <div className="mx-auto w-full max-w-6xl px-6 pb-24 pt-10">
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
            <Link href="/" className="text-xl font-semibold tracking-tight text-ink transition-colors hover:text-cue">
              Cue
            </Link>
          </div>
          <div className="flex items-center gap-4">
            {/* Printed on the mat like the maker's brand. */}
            <span
              aria-hidden="true"
              className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-chalk/70 sm:block"
            >
              Control room · mat nº 001 · 24″ × 18″
            </span>
            <button
              onClick={() => setKeyPanelOpen((open) => !open)}
              aria-expanded={keyPanelOpen}
              className={BTN_QUIET + " px-3 py-1.5"}
            >
              {elKey ? (keyStatus === "bad" ? "Key: check it" : "Key: yours") : "Use your key"}
            </button>
            <button onClick={handleClearMat} className={BTN_QUIET + " px-3 py-1.5"}>
              Clear mat
            </button>
          </div>
        </header>

        {keyPanelOpen && (
          <div className="mb-8 rounded border border-edge bg-panel p-4">
            <p className="max-w-[68ch] text-sm leading-relaxed text-ink-2">
              Reads normally spend this studio&apos;s ElevenLabs credits. Paste your own API
              key to spend yours instead. The key rides only your own requests, exists on
              the server just long enough to reach ElevenLabs, and is never written to
              disk, logged, or echoed in an error. By default it lasts until you close
              this tab. The backend is open source, so you can verify every word of this.
              Bonus: the voice pickers switch to your account&apos;s voices, clones included.
            </p>
            <div className="mt-3 flex flex-wrap items-center gap-2">
              {elKey ? (
                <>
                  <span className="font-mono text-xs text-chalk">
                    {keyStatus === "bad"
                      ? "ElevenLabs is rejecting your saved key. Replace or remove it."
                      : "Using your key. Your credits, your voices."}
                  </span>
                  <button onClick={handleRemoveKey} className={BTN_QUIET + " px-3 py-1.5"}>
                    Remove key
                  </button>
                </>
              ) : (
                <>
                  <input
                    aria-label="Your ElevenLabs API key"
                    type="password"
                    value={keyInput}
                    onChange={(e) => setKeyInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleSaveKey();
                    }}
                    placeholder="xi-..."
                    className={FIELD + " max-w-xs py-2 font-mono text-xs"}
                  />
                  <button
                    onClick={handleSaveKey}
                    disabled={keyStatus === "checking" || keyInput.trim() === ""}
                    className={BTN_QUIET + " px-3 py-1.5"}
                  >
                    {keyStatus === "checking" ? "Checking…" : "Save key"}
                  </button>
                  <label className="flex cursor-pointer items-center gap-1.5 font-mono text-xs text-ink-3">
                    <input
                      type="checkbox"
                      checked={rememberKey}
                      onChange={(e) => setRememberKey(e.target.checked)}
                      className="accent-[var(--cue)]"
                    />
                    remember on this device
                  </label>
                  {keyStatus === "bad" && (
                    <span className="font-mono text-xs text-danger">
                      ElevenLabs rejected that key.
                    </span>
                  )}
                </>
              )}
            </div>
          </div>
        )}

        <p className="mb-8 max-w-[62ch] text-sm leading-relaxed text-chalk">
          Paste a script, one line per row, and give a single direction in plain English.
          The brain reads the whole script and performs each line for where it sits in the
          arc. Prefix a line with a name (<span className="font-mono">ALICE:</span>) to make
          it a conversation and give each character their own voice.
        </p>

        <div className="relative">
          <CornerMarks />
          <div className="grid items-start gap-6 lg:grid-cols-[400px_minmax(0,1fr)]">
            {/* The writer's room: chat with the brain to develop the material. */}
            <div className="order-last lg:order-first lg:sticky lg:top-8">
              <Panel title="Writer's room" meta="chat · drafts">
                <div ref={threadRef} className="flex max-h-[55dvh] min-h-[160px] flex-col gap-3 overflow-y-auto pr-1">
                  {chatLog.length === 0 && (
                    <p className="text-sm leading-relaxed text-ink-3">
                      Describe a scene, like <span className="font-mono">“two rival chefs, one kitchen”</span>,
                      and I&apos;ll draft it. Then direct the draft like a writer: “shorter”,
                      “angrier ending”, “make BOB apologetic”.
                    </p>
                  )}
                  {chatLog.map((turn, i) =>
                    turn.role === "user" ? (
                      <p key={i} className="font-mono text-xs leading-relaxed text-chalk">
                        <span className="text-ink-3">&gt; </span>
                        {turn.text}
                      </p>
                    ) : (
                      <div key={i} className="flex flex-col gap-2">
                        <p className="text-sm leading-relaxed text-ink-2">{turn.text}</p>
                        {turn.script && (
                          <div className="rounded border border-edge bg-panel-2 p-2.5">
                            <pre className="whitespace-pre-wrap font-mono text-xs leading-relaxed text-ink">
                              {turn.script}
                            </pre>
                            <button
                              onClick={() => useDraft(turn.script!)}
                              className={BTN_QUIET + " mt-2 py-1.5"}
                            >
                              Use as script →
                            </button>
                          </div>
                        )}
                      </div>
                    )
                  )}
                  {chatting && <p className="font-mono text-xs text-chalk">writing…</p>}
                </div>
                <div className="mt-3 flex gap-2">
                  <input
                    aria-label="Message the writer's room"
                    value={chatInput}
                    onChange={(e) => setChatInput(e.target.value)}
                    onKeyDown={(e) => {
                      if (e.key === "Enter") handleChat();
                    }}
                    placeholder="describe a scene, or ask for changes"
                    className={FIELD + " py-2 text-sm"}
                  />
                  <button
                    onClick={handleChat}
                    disabled={chatting || chatInput.trim() === ""}
                    className={BTN_QUIET + " shrink-0"}
                  >
                    Send
                  </button>
                </div>
              </Panel>
            </div>

            {/* Production: the script and everything that performs it. */}
            <div className="flex flex-col gap-5">
            {/* The material: the script itself. */}
            <Panel title="Script" meta={lines.length > 0 ? `${lines.length} lines` : "or draft one in the writer's room"}>
              <textarea
                id="script"
                aria-label="Script"
                value={script}
                onChange={(e) => setScript(e.target.value)}
                rows={6}
                placeholder={"It was already too late.\nALICE: Where were you?\nBOB: ...out."}
                className={FIELD + " resize-y"}
              />
            </Panel>

            {/* The direction and the narrator's voice, side by side. */}
            <div className="grid gap-5 sm:grid-cols-[1fr_240px]">
              <Panel title="Direction">
                <input
                  id="direction"
                  aria-label="Direction"
                  value={direction}
                  onChange={(e) => setDirection(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === "Enter") handleDirect();
                  }}
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
                <span className="font-mono text-xs text-chalk">interpreting every line…</span>
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
                  {musicTracks.length > 0 && (
                    <select
                      aria-label="Music bed"
                      value={music}
                      onChange={(e) => {
                        setMusic(e.target.value);
                        setReadTrack(null); // the stitched track no longer matches
                      }}
                      className="cursor-pointer rounded border border-edge bg-panel-2 px-3 py-2 font-mono text-xs text-ink-2 outline-none focus:border-cue-deep"
                    >
                      <option value="">no music</option>
                      {musicTracks.map((t) => (
                        <option key={t.id} value={t.id}>
                          ♫ {t.name}
                        </option>
                      ))}
                    </select>
                  )}
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
                          <p className="text-[15px] leading-relaxed text-ink">
                            {line.delivery ? <Performance delivery={line.delivery} /> : line.text}
                          </p>
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

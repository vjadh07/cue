// The script editor needs state, click handlers, fetch, and an audio element —
// all browser-only — so this is a Client Component.
"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { Tour } from "./tour";

// Where the Python backend is listening. For now this is hard-coded.
// Where the backend lives. Defaults to the local dev server; set
// NEXT_PUBLIC_BACKEND_URL to your deployed backend for production.
const BACKEND_URL = process.env.NEXT_PUBLIC_BACKEND_URL ?? "http://localhost:8000";

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

// What the booth's ears measured off a rendered clip (shape /analyze returns).
type Measured = {
  loudness_db: number;
  pitch_hz: number | null;
  brightness_hz: number;
  energy: number;
  duration_ms: number;
  words_per_sec: number | null;
};

// One judged take from the self-directing loop (shape /perform returns):
// which attempt it was, what the plan aimed for, what the ears heard.
type ReportTake = {
  take: number; // 1-based
  action: "plan" | "reroll" | "redirect";
  audio_id: string;
  ext: string;
  score: { target: number; measured: number; delta: number; passed: boolean; hint: string | null };
};

// One line's account in the loop's report: the target it was directed to,
// every take tried, and which one shipped.
type ReportLine = {
  text: string;
  speaker: string;
  target: number;
  passed: boolean;
  engine_limited: boolean;
  kept_take: number; // 1-based index into takes
  takes: ReportTake[];
};

// The whole self-directed read, honestly accounted.
type PerformReport = {
  total_lines: number;
  passed_lines: number;
  total_renders: number;
  arc_correlation: number | null;
  lines: ReportLine[];
};

// One take of a line: an interpretation, plus (once rendered and analyzed)
// the clip it produced and what the booth heard in it. Take 1 comes from
// Direct; later takes are retakes, each born from a director's note.
type Take = {
  settings: Settings;
  tags: string[];
  notes: string;
  delivery: string | null;
  brain: string;
  note?: string; // the note that asked for this take (absent on take 1)
  audioId?: string;
  audioExt?: string;
  measured?: Measured;
};

// A line on the workbench: what /direct returned, plus its take history.
type LineState = DirectedLine & { takes: Take[]; active: number };

function firstTake(line: DirectedLine): Take {
  return {
    settings: line.settings,
    tags: line.tags,
    notes: line.notes,
    delivery: line.delivery,
    brain: line.brain,
  };
}

function takeOf(line: LineState): Take {
  return line.takes[line.active];
}

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
  anchor,
}: {
  title: string;
  meta?: string;
  children: React.ReactNode;
  anchor?: string; // data-tour target, for the guided tour spotlight
}) {
  return (
    <section
      data-tour={anchor}
      className="rounded border border-edge bg-panel shadow-[0_2px_0_rgba(0,0,0,0.25)]"
    >
      <header className="flex items-baseline justify-between gap-3 border-b border-edge px-3 py-2">
        <h2 className="font-mono text-[11px] uppercase tracking-[0.14em] text-ink-3">{title}</h2>
        {meta && <span className="font-mono text-[10px] text-ink-3">{meta}</span>}
      </header>
      <div className="p-3">{children}</div>
    </section>
  );
}

// The measuring strip along the top edge: a solid graphite bezel framing
// the sky below it, so the tick numbers stay crisp no matter what cloud
// would otherwise sit behind them.
function Ruler() {
  return (
    <div
      aria-hidden="true"
      className="flex h-5 select-none overflow-hidden border-b border-edge-strong bg-mat"
    >
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
  const [lines, setLines] = useState<LineState[]>([]);
  const [directing, setDirecting] = useState(false);
  // Which line has a retake being interpreted right now (its Retake button
  // shows progress); null = none.
  const [retakingLine, setRetakingLine] = useState<number | null>(null);
  // The note drafts, one per line strip.
  const [noteDrafts, setNoteDrafts] = useState<Record<number, string>>({});
  const [errorMessage, setErrorMessage] = useState("");

  // The actor: voices come from the backend (your ElevenLabs account), and
  // `voice` is the selected voice_id, sent to /render at playback.
  const [voices, setVoices] = useState<Voice[]>([]);
  const [voice, setVoice] = useState("");

  // The local clone engine cold-starts (~30s) on its first render this
  // session while its weights load. Once one local clip comes back we've
  // warmed up, and later renders are quick — so the "warming up" hint only
  // shows the first time.
  const [localWarm, setLocalWarm] = useState(false);

  // The guided tour: auto-opens once on a first visit, reopenable any time.
  const [tourOpen, setTourOpen] = useState(false);

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

  // Screenplay import: the hidden file input, the action-lines toggle, and
  // the "Imported 'Title': N characters" note after a successful import.
  const fountainInputRef = useRef<HTMLInputElement>(null);
  const [includeAction, setIncludeAction] = useState(false);
  const [importNote, setImportNote] = useState("");

  // Your voice: record (or upload) a sample, then clone it in the visitor's
  // own ElevenLabs account. The sample never goes anywhere without consent.
  const [recordingVoice, setRecordingVoice] = useState(false);
  const [recordSecs, setRecordSecs] = useState(0);
  const [voiceSample, setVoiceSample] = useState<{ blob: Blob; name: string } | null>(null);
  const [voiceSampleUrl, setVoiceSampleUrl] = useState("");
  const [cloneName, setCloneName] = useState("");
  const [cloneConsent, setCloneConsent] = useState(false);
  const [cloning, setCloning] = useState(false);
  const [cloneNote, setCloneNote] = useState("");
  const recorderRef = useRef<MediaRecorder | null>(null);
  const recordChunksRef = useRef<Blob[]>([]);
  const recordTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const voiceFileRef = useRef<HTMLInputElement>(null);
  // Bumped after a successful clone so the voice pickers reload with it.
  const [voicesTick, setVoicesTick] = useState(0);

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
  // The self-directing loop: when on, the full read goes through /perform,
  // where Cue listens to every take and retries the lines that miss.
  const [selfDirect, setSelfDirect] = useState(false);
  const [performReport, setPerformReport] = useState<PerformReport | null>(null);

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
    // First visit ever? Open the guided tour once.
    try {
      if (!localStorage.getItem("cue-tour-seen")) setTourOpen(true);
    } catch {
      /* best-effort */
    }
    hydrated.current = true;
  }, []);

  // Close the tour and remember it's been seen (the header button reopens it).
  function closeTour() {
    setTourOpen(false);
    try {
      localStorage.setItem("cue-tour-seen", "1");
    } catch {
      /* best-effort */
    }
  }

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
  }, [elKey, voicesTick]);

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

  // --- Your voice: record a sample and clone it in the visitor's account ---

  async function startVoiceRecording() {
    try {
      // Capture your ACTUAL voice, not the browser's call-optimized version.
      // Echo cancellation, noise suppression, and auto-gain are on by default
      // and alter your timbre — great for video calls, bad for a voice clone.
      // Off, plus a high bitrate, gives the model a faithful reference.
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: {
          echoCancellation: false,
          noiseSuppression: false,
          autoGainControl: false,
          channelCount: 1,
        },
      });
      const recorder = new MediaRecorder(stream, { audioBitsPerSecond: 256000 });
      recordChunksRef.current = [];
      recorder.ondataavailable = (e) => recordChunksRef.current.push(e.data);
      recorder.onstop = () => {
        stream.getTracks().forEach((t) => t.stop());
        const blob = new Blob(recordChunksRef.current, { type: recorder.mimeType || "audio/webm" });
        setVoiceSample({ blob, name: "my-voice.webm" });
        setVoiceSampleUrl((old) => {
          if (old) URL.revokeObjectURL(old);
          return URL.createObjectURL(blob);
        });
      };
      recorderRef.current = recorder;
      recorder.start();
      setRecordingVoice(true);
      setRecordSecs(0);
      setCloneNote("");
      recordTimerRef.current = setInterval(() => setRecordSecs((s) => s + 1), 1000);
    } catch {
      setErrorMessage("Microphone access was blocked. You can upload a recording instead.");
    }
  }

  function stopVoiceRecording() {
    recorderRef.current?.stop();
    setRecordingVoice(false);
    if (recordTimerRef.current) clearInterval(recordTimerRef.current);
  }

  async function handleCloneVoice() {
    if (!voiceSample || !cloneName.trim() || !cloneConsent || cloning) return;
    setErrorMessage("");
    setCloning(true);
    try {
      const form = new FormData();
      form.append("name", cloneName.trim());
      form.append("consent", "true");
      form.append("files", voiceSample.blob, voiceSample.name);
      // No key, no headers: cloning is local. The browser sets the multipart
      // boundary; the sample never leaves this machine.
      const response = await fetch(`${BACKEND_URL}/voice/clone`, {
        method: "POST",
        body: form,
      });
      if (!response.ok) {
        const body = await response.json().catch(() => null);
        throw new Error(body?.detail ?? `Backend responded with ${response.status}`);
      }
      setCloneNote(`“${cloneName.trim()}” is in your cast now. Pick it like any other voice.`);
      setVoiceSample(null);
      setVoiceSampleUrl((old) => {
        if (old) URL.revokeObjectURL(old);
        return "";
      });
      setCloneName("");
      setCloneConsent(false);
      setVoicesTick((t) => t + 1); // the pickers reload and include the clone
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? `Couldn't clone the voice: ${err.message}` : "Couldn't clone the voice."
      );
    } finally {
      setCloning(false);
    }
  }

  // Forget a locally-cloned voice: delete it on the backend, drop any
  // selection pointing at it (narrator or cast), and reload the pickers.
  async function handleDeleteClone(voiceId: string, voiceName: string) {
    if (!window.confirm(`Delete “${voiceName}”? This removes the voice from this machine.`)) return;
    setErrorMessage("");
    try {
      const response = await fetch(`${BACKEND_URL}/voice/clone/${encodeURIComponent(voiceId)}`, {
        method: "DELETE",
      });
      if (!response.ok && response.status !== 404) {
        throw new Error(`Backend responded with ${response.status}`);
      }
      // A deleted voice must not stay selected anywhere, or a render would 500.
      setVoice((prev) => (prev === voiceId ? "" : prev));
      setCast((prev) => {
        const next: Record<string, string> = {};
        for (const [speaker, v] of Object.entries(prev)) next[speaker] = v === voiceId ? "" : v;
        return next;
      });
      setReadTrack(null);
      setCloneNote("");
      setVoicesTick((t) => t + 1); // reload the pickers without the deleted voice
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? `Couldn't delete the voice: ${err.message}` : "Couldn't delete the voice."
      );
    }
  }

  // A ready-made scene, so a first visit never starts at an empty box. Free
  // until Direct is pressed.
  function loadSampleScene() {
    useDraft(
      [
        "NORA: You kept the letter.",
        "ELI: I kept everything.",
        "NORA: Then why did you never write back?",
        "ELI: Because you moved on. And I didn't.",
      ].join("\n")
    );
    setDirection("an old wound reopening, tender but tense");
    setImportNote("");
  }

  // Import a real screenplay (.fountain): the backend parses it into Cue's
  // native script (merging DEV (V.O.) into DEV, carrying parentheticals as
  // per-line hints) and it lands in the Script box like any other draft.
  async function handleImportScreenplay(file: File) {
    setErrorMessage("");
    setImportNote("");
    try {
      const text = await file.text();
      const response = await fetch(`${BACKEND_URL}/import/fountain`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text, include_action: includeAction }),
      });
      if (response.status === 400) {
        setErrorMessage("That file has no performable lines. Is it a screenplay?");
        return;
      }
      if (!response.ok) throw new Error(`Backend responded with ${response.status}`);
      const data: {
        script: string;
        title: string | null;
        characters: string[];
        dialogue_lines: number;
      } = await response.json();
      useDraft(data.script);
      setImportNote(
        `Imported ${data.title ? `“${data.title}”` : "screenplay"}: ` +
          `${data.characters.length} character${data.characters.length === 1 ? "" : "s"}, ` +
          `${data.dialogue_lines} lines. Now cast and direct it.`
      );
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? `Couldn't import that file: ${err.message}` : "Couldn't import that file."
      );
    }
  }

  // Move a draft from the writer's room into production.
  function useDraft(draft: string) {
    setScript(draft);
    // A new script invalidates the old read: clear the directed lines/track.
    setLines([]);
    setReadTrack(null);
    setPerformReport(null);
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
    setPerformReport(null);

    try {
      const response = await fetch(`${BACKEND_URL}/direct`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ script, direction }),
      });
      if (!response.ok) throw new Error(`Backend responded with ${response.status}`);
      const data: { lines: DirectedLine[]; speakers: string[] } = await response.json();
      setLines(data.lines.map((line) => ({ ...line, takes: [firstTake(line)], active: 0 })));
      setNoteDrafts({});
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
  function voiceFor(line: LineState) {
    return line.speaker ? cast[line.speaker] ?? voice : voice;
  }

  // A local clone voice_id (Cue's on-device engine), which cold-starts.
  const isLocalVoice = (v: string) => v.startsWith("local:");

  // Store a change into one take of one line, immutably.
  function patchTake(lineIndex: number, takeIndex: number, patch: Partial<Take>) {
    setLines((prev) =>
      prev.map((line, i) =>
        i === lineIndex
          ? {
              ...line,
              takes: line.takes.map((t, k) => (k === takeIndex ? { ...t, ...patch } : t)),
            }
          : line
      )
    );
  }

  // The booth listens to a rendered clip (local DSP on the backend, free)
  // and the measurements land on the take that produced it.
  async function analyzeTake(lineIndex: number, takeIndex: number, audioId: string, ext: string) {
    try {
      const response = await fetch(`${BACKEND_URL}/analyze`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ audio_id: audioId, ext, text: lines[lineIndex]?.text ?? "" }),
      });
      if (!response.ok) return; // measurements are a bonus, never an error
      const measured: Measured = await response.json();
      patchTake(lineIndex, takeIndex, { measured, audioId, audioExt: ext });
    } catch {
      /* the booth stays quiet rather than breaking playback */
    }
  }

  // A director's note against one line: the brain re-reads that line (with
  // the whole script still in view) and the result lands as the next take.
  async function handleRetake(i: number) {
    const note = (noteDrafts[i] ?? "").trim();
    if (!note || retakingLine !== null) return;
    setErrorMessage("");
    setRetakingLine(i);
    try {
      const response = await fetch(`${BACKEND_URL}/retake`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          script: lines.map((l) => l.text),
          index: i,
          direction,
          note,
        }),
      });
      if (!response.ok) throw new Error(`Backend responded with ${response.status}`);
      const take: Take = { ...(await response.json()), note };
      setLines((prev) =>
        prev.map((line, k) =>
          k === i ? { ...line, takes: [...line.takes, take], active: line.takes.length } : line
        )
      );
      setNoteDrafts((prev) => ({ ...prev, [i]: "" }));
      setReadTrack(null); // the stitched track no longer matches the kept takes
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? `Couldn't get a retake: ${err.message}` : "Couldn't get a retake."
      );
    } finally {
      setRetakingLine(null);
    }
  }

  // Play one line: render it with the settings/tags it already got from /direct,
  // then play. Reusing the same <audio> means a new Play interrupts the last.
  async function handlePlay(i: number) {
    const line = lines[i];
    const take = takeOf(line);
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
          settings: take.settings,
          tags: take.tags,
          voice: lineVoice,
          delivery: take.delivery ?? "",
        }),
      });
      if (!response.ok) throw new Error(`Render failed (${response.status})`);
      const data = { audio_id: "", ext: "", ...(await response.json()) };
      if (isLocalVoice(lineVoice)) setLocalWarm(true); // model is loaded now

      // The booth listens in the background while the clip plays.
      analyzeTake(i, line.active, data.audio_id, data.ext);

      const audio = audioRef.current;
      if (!audio) throw new Error("Audio player not ready.");
      audio.src = `${BACKEND_URL}/audio/${data.audio_id}.${data.ext}`;
      audio.volume = take.settings.volume;
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
            settings: takeOf(line).settings,
            tags: takeOf(line).tags,
            voice: voiceFor(line),
            delivery: takeOf(line).delivery ?? "",
            speaker: line.speaker ?? "",
          })),
          music,
        }),
      });
      if (!response.ok) throw new Error(`Stitch failed (${response.status})`);
      const data: { audio_id: string; ext: string; clips?: { audio_id: string; ext: string }[] } =
        await response.json();
      setReadTrack(data.audio_id);
      setPerformReport(null); // this track is a plain read; the old report doesn't describe it
      if (lines.some((l) => isLocalVoice(voiceFor(l)))) setLocalWarm(true);

      // The full read hands the booth every line's clip: the measured arc
      // fills in for the whole scene at once.
      (data.clips ?? []).forEach((clip, i) => {
        if (lines[i]) analyzeTake(i, lines[i].active, clip.audio_id, clip.ext);
      });

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

  // The self-directing read: /perform re-plans the scene from the direction,
  // renders every line, listens with the booth's ears, and retries lines that
  // miss the target (a fresh roll first, then a re-direct born from the miss).
  // Back comes the stitched best takes plus an honest per-take report.
  async function handlePerform() {
    setErrorMessage("");
    setStitching(true);
    pendingLine.current = -1; // the full read, not an individual line

    try {
      const script = lines
        .map((line) => (line.speaker ? `${line.speaker}: ${line.text}` : line.text))
        .join("\n");
      const response = await fetch(`${BACKEND_URL}/perform`, {
        method: "POST",
        headers: { "Content-Type": "application/json", ...keyHeader },
        body: JSON.stringify({ script, direction, voice, cast, music }),
      });
      if (!response.ok) throw new Error(`Perform failed (${response.status})`);
      const data: { audio_id: string; ext: string; report: PerformReport } = await response.json();
      setReadTrack(data.audio_id);
      setPerformReport(data.report);
      if (lines.some((l) => isLocalVoice(voiceFor(l)))) setLocalWarm(true);

      // The kept takes feed the booth too, so the measured arc fills in.
      data.report.lines.forEach((line, i) => {
        const kept = line.takes[line.kept_take - 1];
        if (kept && lines[i]) analyzeTake(i, lines[i].active, kept.audio_id, kept.ext);
      });

      const audio = audioRef.current;
      if (!audio) throw new Error("Audio player not ready.");
      audio.src = `${BACKEND_URL}/audio/${data.audio_id}.${data.ext}`;
      audio.volume = 1.0;
      await audio.play();
    } catch (err) {
      setErrorMessage(
        err instanceof Error ? `Couldn't perform the read: ${err.message}` : "Couldn't perform the read."
      );
    } finally {
      setStitching(false);
    }
  }

  // Hear one take from the report: the loop's audition tape, clip by clip.
  function playTakeClip(take: ReportTake) {
    const audio = audioRef.current;
    if (!audio) return;
    pendingLine.current = -2; // a report clip: the meter dances, no line lights up
    audio.src = `${BACKEND_URL}/audio/${take.audio_id}.${take.ext}`;
    audio.volume = 1.0;
    audio.play().catch(() => setErrorMessage("Couldn't play that take."));
  }

  const anyPlaying = playingLine !== null;
  const readPlaying = playingLine === -1;
  // The distinct named characters in the directed script, in first-seen order.
  const castList = Array.from(
    new Set(lines.map((l) => l.speaker).filter((s): s is string => Boolean(s)))
  );

  return (
    <main className="relative z-[1] min-h-[100dvh]">
      {/* The ruler along the top edge, over the sky. */}
      <Ruler />

      {/* The readout: a frosted graphite strip over the sky, holding
          everything before the tool panels (which have their own solid
          backgrounds and don't need it). Keeps header/intro/stage-strip
          text legible over the cloud background without per-pixel luck. */}
      <div className="mx-auto w-full max-w-6xl px-6 pb-24 pt-10">
        <div className="mb-8 rounded-lg border border-edge bg-mat/75 px-6 pb-6 pt-8 backdrop-blur-md sm:px-8">
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
            {/* Printed on the readout like the maker's brand. */}
            <span
              aria-hidden="true"
              className="hidden font-mono text-[10px] uppercase tracking-[0.18em] text-chalk/70 sm:block"
            >
              Control room · console nº 001 · 24-track
            </span>
            <button onClick={() => setTourOpen(true)} className={BTN_QUIET + " px-3 py-1.5"}>
              How it works
            </button>
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

        <p className="mb-5 max-w-[62ch] text-sm leading-relaxed text-chalk">
          Paste a script, one line per row, and give a single direction in plain English.
          The brain reads the whole script and performs each line for where it sits in the
          arc. Prefix a line with a name (<span className="font-mono">ALICE:</span>) to make
          it a conversation and give each character their own voice.
        </p>

        {/* Where you are in the session: the four stages of a read, with the
            current one lit. Navigation for first-timers, a checklist for the rest. */}
        {(() => {
          const stage = readTrack ? 3 : lines.length > 0 ? 2 : script.trim() ? 1 : 0;
          const steps: { label: string; hint: string }[] = [
            { label: "write", hint: "draft in the writer's room, paste, or load the sample scene" },
            { label: "direct", hint: "give one plain-English note and press Direct" },
            { label: "cast & retake", hint: "assign voices, play lines, give notes for another take" },
            { label: "produce", hint: "play the full read, then download the mp3 and subtitles" },
          ];
          return (
            <div data-tour="stages" className="mb-8 flex flex-wrap items-baseline gap-x-4 gap-y-1">
              {steps.map((step, i) => (
                <span key={step.label} className="flex items-baseline gap-4 font-mono text-[11px] uppercase tracking-[0.12em]">
                  <span
                    className={
                      i < stage ? "text-chalk/70" : i === stage ? "text-cue" : "text-ink-3"
                    }
                  >
                    {i < stage ? "✓ " : ""}
                    {String(i + 1).padStart(2, "0")} {step.label}
                  </span>
                  {i < steps.length - 1 && <span className="text-ink-3">·</span>}
                </span>
              ))}
              <span className="basis-full font-mono text-[11px] text-ink-3 sm:basis-auto">
                → {steps[stage].hint}
              </span>
            </div>
          );
        })()}
        </div>

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
            <Panel anchor="script" title="Script" meta={lines.length > 0 ? `${lines.length} lines` : "or draft one in the writer's room"}>
              <textarea
                id="script"
                aria-label="Script"
                value={script}
                onChange={(e) => setScript(e.target.value)}
                rows={6}
                placeholder={"It was already too late.\nALICE: Where were you?\nBOB: ...out."}
                className={FIELD + " resize-y"}
              />
              {/* Table read: bring a real screenplay. Fountain is what Highland,
                  WriterDuet, and Final Draft all export as plain text. */}
              <div className="mt-2 flex flex-wrap items-center gap-3">
                <input
                  ref={fountainInputRef}
                  type="file"
                  accept=".fountain,.txt,.spmd"
                  className="hidden"
                  aria-label="Screenplay file"
                  onChange={(e) => {
                    const file = e.target.files?.[0];
                    if (file) handleImportScreenplay(file);
                    e.target.value = ""; // allow re-importing the same file
                  }}
                />
                <button
                  onClick={() => fountainInputRef.current?.click()}
                  className={BTN_QUIET + " px-3 py-1.5"}
                >
                  Import screenplay (.fountain)
                </button>
                <label className="flex cursor-pointer items-center gap-1.5 font-mono text-xs text-ink-3">
                  <input
                    type="checkbox"
                    checked={includeAction}
                    onChange={(e) => setIncludeAction(e.target.checked)}
                    className="accent-[var(--cue)]"
                  />
                  narrator reads action lines
                </label>
                {importNote && <span className="font-mono text-xs text-chalk">{importNote}</span>}
                {!script.trim() && (
                  <button onClick={loadSampleScene} className={BTN_QUIET + " px-3 py-1.5"}>
                    Load a sample scene
                  </button>
                )}
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

            {/* Your voice: the creator loop's missing piece. Record a minute
                once, and Cue's own local engine learns your voice — nothing
                leaves this machine. */}
            <Panel anchor="voice" title="Your voice" meta="local · never uploaded">
                <div className="flex flex-col gap-3">
                  <p className="max-w-[62ch] text-sm leading-relaxed text-ink-2">
                    Hate recording voiceovers? Record about a minute of yourself once, and
                    Cue&apos;s own voice engine learns how you sound and performs every script
                    as you. It runs entirely on this machine: your voice sample and every
                    generated clip stay here, and each clip carries an inaudible
                    AI-generated watermark.
                  </p>

                  {/* Voices you've already cloned, with a way to forget each. */}
                  {voices.some((v) => isLocalVoice(v.id)) && (
                    <div className="flex flex-col gap-1.5 rounded border border-edge bg-panel-2 p-2.5">
                      <span className="font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
                        Your saved voices
                      </span>
                      {voices
                        .filter((v) => isLocalVoice(v.id))
                        .map((v) => {
                          const label = v.name.replace(/\s*·.*$/, "");
                          return (
                            <div key={v.id} className="flex items-center justify-between gap-3">
                              <span className="truncate text-sm text-ink-2">{label}</span>
                              <button
                                onClick={() => handleDeleteClone(v.id, label)}
                                aria-label={`Delete ${label}`}
                                className="shrink-0 rounded border border-edge px-2 py-0.5 font-mono text-[11px] text-ink-3 transition-colors hover:border-danger hover:text-danger"
                              >
                                Delete
                              </button>
                            </div>
                          );
                        })}
                    </div>
                  )}

                  <div className="flex flex-wrap items-center gap-3">
                    {recordingVoice ? (
                      <button onClick={stopVoiceRecording} className={BTN_PRIMARY + " px-4 py-2"}>
                        ■ Stop ({Math.floor(recordSecs / 60)}:{String(recordSecs % 60).padStart(2, "0")})
                      </button>
                    ) : (
                      <button onClick={startVoiceRecording} className={BTN_QUIET + " px-3 py-1.5"}>
                        ● Record your voice
                      </button>
                    )}
                    <input
                      ref={voiceFileRef}
                      type="file"
                      accept="audio/*"
                      className="hidden"
                      aria-label="Voice sample file"
                      onChange={(e) => {
                        const file = e.target.files?.[0];
                        if (file) {
                          setVoiceSample({ blob: file, name: file.name });
                          setVoiceSampleUrl((old) => {
                            if (old) URL.revokeObjectURL(old);
                            return URL.createObjectURL(file);
                          });
                          setCloneNote("");
                        }
                        e.target.value = "";
                      }}
                    />
                    <button
                      onClick={() => voiceFileRef.current?.click()}
                      className={BTN_QUIET + " px-3 py-1.5"}
                    >
                      or upload a recording
                    </button>
                    <span className="font-mono text-[10px] text-ink-3">
                      ~30s of natural talking. A quiet room matters: Cue captures
                      your raw voice, so background noise isn&apos;t filtered out.
                    </span>
                  </div>

                  {voiceSample && (
                    <div className="flex flex-wrap items-center gap-3">
                      <audio controls src={voiceSampleUrl} className="h-9 max-w-60" />
                      <input
                        aria-label="Name for your voice"
                        value={cloneName}
                        onChange={(e) => setCloneName(e.target.value)}
                        placeholder="name it: My voice"
                        className={FIELD + " max-w-44 py-1.5 text-sm"}
                      />
                      <label className="flex cursor-pointer items-center gap-1.5 font-mono text-xs text-ink-3">
                        <input
                          type="checkbox"
                          checked={cloneConsent}
                          onChange={(e) => setCloneConsent(e.target.checked)}
                          className="accent-[var(--cue)]"
                        />
                        this is my own voice, and I consent to cloning it
                      </label>
                      <button
                        onClick={handleCloneVoice}
                        disabled={cloning || !cloneName.trim() || !cloneConsent}
                        className={BTN_PRIMARY + " px-4 py-2"}
                      >
                        {cloning ? "Cloning…" : "Create my voice"}
                      </button>
                    </div>
                  )}
                  {cloneNote && <p className="font-mono text-xs text-cue">{cloneNote}</p>}
                </div>
            </Panel>

            <div className="flex items-center gap-4">
              <button data-tour="direct" onClick={handleDirect} disabled={directing || script.trim() === ""} className={BTN_PRIMARY}>
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
                  <button
                    onClick={selfDirect ? handlePerform : handleRead}
                    disabled={stitching}
                    className={BTN_PRIMARY}
                  >
                    {stitching
                      ? lines.some((l) => isLocalVoice(voiceFor(l))) && !localWarm
                        ? "Warming up… (~30s)"
                        : selfDirect
                          ? "Directing takes…"
                          : "Stitching…"
                      : readPlaying
                        ? "Playing…"
                        : selfDirect
                          ? "▶ Perform, self-directed"
                          : "▶ Play full read"}
                  </button>
                  <button
                    onClick={() => setSelfDirect((v) => !v)}
                    aria-pressed={selfDirect}
                    title="Cue listens to every take it performs and retries the lines that miss your direction. Up to 3 takes a line."
                    className={
                      BTN_QUIET + (selfDirect ? " border-cue-deep bg-cue/10 text-cue" : "")
                    }
                  >
                    {selfDirect ? "● " : "○ "}Direct until it lands
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
                    <>
                      <a href={`${BACKEND_URL}/audio/${readTrack}.mp3?download=1`} className={BTN_QUIET}>
                        Download
                      </a>
                      <a
                        href={`${BACKEND_URL}/captions/${readTrack}.srt?download=1`}
                        className={BTN_QUIET}
                        title="Frame-accurate subtitles, straight from the stitcher's timeline"
                      >
                        Subtitles .srt
                      </a>
                    </>
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
                {selfDirect && (
                  <p className="mt-2 max-w-[68ch] font-mono text-[10px] leading-relaxed text-ink-3">
                    Cue re-plans the scene from your direction, listens to every take with its own
                    ears, and retries what misses: a fresh roll first, then a re-direct born from
                    the miss. Three takes a line at most, and the best one ships.
                  </p>
                )}
              </Panel>
            )}

            {/* The take report: the loop's honest account of a self-directed
                read. One row per line; every chip is a real take you can hear. */}
            {performReport && lines.length > 0 && (
              <Panel
                title="Take report"
                meta={
                  `${performReport.passed_lines}/${performReport.total_lines} landed · ` +
                  `${performReport.total_renders} renders` +
                  (performReport.arc_correlation !== null
                    ? ` · arc r ${performReport.arc_correlation.toFixed(2)}`
                    : "")
                }
              >
                <div className="flex flex-col gap-2">
                  {performReport.lines.map((line, i) => (
                    <div key={i} className="flex flex-wrap items-center gap-2">
                      <span className="w-16 shrink-0 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
                        L{String(i + 1).padStart(2, "0")}
                        <span className={line.passed ? "text-cue" : ""}>
                          {line.passed ? " ✓" : " ·"}
                        </span>
                      </span>
                      {line.takes.map((t) => {
                        const kept = t.take === line.kept_take;
                        return (
                          <button
                            key={t.take}
                            onClick={() => playTakeClip(t)}
                            title={
                              (t.score.passed ? "landed" : t.score.hint ?? "missed") +
                              ` · click to hear this take`
                            }
                            className={
                              "rounded border px-2 py-1 font-mono text-[10px] transition-colors duration-150 active:translate-y-px " +
                              (kept
                                ? "border-cue-deep bg-cue/15 text-cue"
                                : "border-edge bg-panel-2 text-ink-2 hover:border-cue-deep hover:text-cue")
                            }
                          >
                            T{t.take} {t.action} {t.score.measured.toFixed(2)}
                            {kept ? " ★" : ""}
                          </button>
                        );
                      })}
                      <span className="font-mono text-[10px] text-ink-3">
                        aim {line.target.toFixed(2)}
                      </span>
                      {line.engine_limited && (
                        <span
                          title="This voice can't push further on this direction, so Cue kept the closest take instead of burning another render."
                          className="rounded border border-edge px-1.5 py-0.5 font-mono text-[9px] uppercase tracking-[0.08em] text-ink-3"
                        >
                          engine limit
                        </span>
                      )}
                    </div>
                  ))}
                  <p className="mt-1 max-w-[68ch] font-mono text-[10px] leading-relaxed text-ink-3">
                    Every take Cue tried, measured on the same 0 to 1 intensity scale it was
                    directed on. ★ marks the take that shipped. Click any chip to hear that take.
                  </p>
                </div>
              </Panel>
            )}

            {/* The booth: the scene's emotional arc, planned vs measured.
                Planned = the brain's intensity per line (1 - stability).
                Measured = what the ears actually heard in the rendered clip.
                If the direction said "build", both should climb. */}
            {lines.length > 1 && (
              <Panel title="Booth" meta="planned vs measured energy">
                <div className="flex items-end gap-3 overflow-x-auto pb-1">
                  {lines.map((line, i) => {
                    const planned = 1 - takeOf(line).settings.stability;
                    const measured = takeOf(line).measured?.energy;
                    return (
                      <div key={i} className="flex shrink-0 flex-col items-center gap-1.5">
                        <div className="flex h-24 items-end gap-1">
                          <span
                            title={`planned intensity ${planned.toFixed(2)}`}
                            className="w-3 rounded-sm border border-cue-deep/70 bg-transparent"
                            style={{ height: `${Math.max(4, Math.round(planned * 100))}%` }}
                          />
                          <span
                            title={
                              measured !== undefined
                                ? `measured energy ${measured.toFixed(2)}`
                                : "not rendered yet"
                            }
                            className={
                              "w-3 rounded-sm " + (measured !== undefined ? "bg-cue/85" : "bg-panel-2")
                            }
                            style={{
                              height: `${measured !== undefined ? Math.max(4, Math.round(measured * 100)) : 4}%`,
                            }}
                          />
                        </div>
                        <span className="font-mono text-[9px] uppercase text-ink-3">
                          L{String(i + 1).padStart(2, "0")}
                        </span>
                      </div>
                    );
                  })}
                  <p className="ml-2 max-w-[26ch] self-center font-mono text-[10px] leading-relaxed text-ink-3">
                    <span className="text-cue">▯</span> what the brain planned ·{" "}
                    <span className="text-cue">▮</span> what the ears heard. Play lines (or the
                    full read) and the measured arc fills in.
                  </p>
                </div>
              </Panel>
            )}

            {/* The directed script: one strip per line, laid out on the mat. */}
            {lines.length > 0 && (
              <div className="flex flex-col gap-3">
                {lines.map((line, i) => {
                  const take = takeOf(line);
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
                        <span className="flex items-baseline gap-2 font-mono text-[10px] uppercase tracking-[0.14em] text-ink-3">
                          L{String(i + 1).padStart(2, "0")}
                          {line.speaker && <span className="text-cue">· {line.speaker}</span>}
                          {/* Take pills: the line's history in the booth. */}
                          {line.takes.length > 1 &&
                            line.takes.map((t, k) => (
                              <button
                                key={k}
                                onClick={() => {
                                  setLines((prev) =>
                                    prev.map((l, li) => (li === i ? { ...l, active: k } : l))
                                  );
                                  setReadTrack(null); // the track no longer matches
                                }}
                                title={t.note ? `note: ${t.note}` : "the first read"}
                                className={
                                  "rounded-sm border px-1.5 py-0.5 font-mono text-[10px] transition-colors duration-150 " +
                                  (line.active === k
                                    ? "border-cue-deep bg-cue text-cue-ink"
                                    : "border-edge text-ink-3 hover:border-cue-deep hover:text-cue")
                                }
                              >
                                T{k + 1}
                              </button>
                            ))}
                        </span>
                        {take.notes && (
                          <span className="truncate font-mono text-[10px] text-ink-3">read as: {take.notes}</span>
                        )}
                      </header>

                      <div className="flex items-start justify-between gap-4 p-3">
                        <div className="min-w-0 flex-col gap-2">
                          <p className="text-[15px] leading-relaxed text-ink">
                            {take.delivery ? <Performance delivery={take.delivery} /> : line.text}
                          </p>
                          <div className="mt-2 flex flex-wrap items-center gap-x-3 gap-y-1.5">
                            {take.tags.map((tag) => (
                              <span
                                key={tag}
                                className="rounded-sm border border-cue-deep/60 bg-cue/10 px-1.5 py-0.5 font-mono text-[10px] text-cue"
                              >
                                [{tag}]
                              </span>
                            ))}
                            <span className="font-mono text-[10px] text-ink-3">
                              {SETTING_KEYS.map(({ key, label }) => `${label} ${take.settings[key].toFixed(2)}`).join(
                                "  ·  "
                              )}
                              {"  ·  "}
                              {take.brain}
                            </span>
                          </div>
                          {/* What the booth heard in this take's clip. */}
                          {take.measured && (
                            <div className="mt-1.5 flex items-center gap-2 font-mono text-[10px] text-ink-3">
                              <span className="h-1.5 w-16 overflow-hidden rounded-sm bg-panel-2">
                                <span
                                  className="block h-full bg-cue/80"
                                  style={{ width: `${Math.round(take.measured.energy * 100)}%` }}
                                />
                              </span>
                              <span>
                                heard: energy {take.measured.energy.toFixed(2)} · {take.measured.loudness_db.toFixed(1)} dB
                                {take.measured.pitch_hz !== null && ` · ${Math.round(take.measured.pitch_hz)} Hz`}
                                {take.measured.words_per_sec !== null && ` · ${take.measured.words_per_sec} w/s`}
                              </span>
                            </div>
                          )}
                        </div>
                        <button onClick={() => handlePlay(i)} disabled={isLoading} className={BTN_QUIET + " shrink-0"}>
                          {isLoading
                            ? isLocalVoice(voiceFor(line)) && !localWarm
                              ? "Warming up… (~30s)"
                              : "Rendering…"
                            : isPlaying
                              ? "Playing…"
                              : "Play"}
                        </button>
                      </div>

                      {/* The director's note: ask this line for another take. */}
                      <footer className="flex items-center gap-2 border-t border-edge px-3 py-2">
                        <input
                          aria-label={`Note for line ${i + 1}`}
                          value={noteDrafts[i] ?? ""}
                          onChange={(e) => setNoteDrafts((prev) => ({ ...prev, [i]: e.target.value }))}
                          onKeyDown={(e) => {
                            if (e.key === "Enter") handleRetake(i);
                          }}
                          placeholder="give a note: colder, more hurt, don't shout it"
                          className={FIELD + " py-1.5 font-mono text-xs"}
                        />
                        <button
                          onClick={() => handleRetake(i)}
                          disabled={retakingLine !== null || !(noteDrafts[i] ?? "").trim()}
                          className={BTN_QUIET + " shrink-0 px-3 py-1.5"}
                        >
                          {retakingLine === i ? "Reading…" : "Retake"}
                        </button>
                      </footer>
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

      {/* The guided tour: spotlights the real controls in order. */}
      <Tour open={tourOpen} onClose={closeTour} />
    </main>
  );
}

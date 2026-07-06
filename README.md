# Cue

Direct an AI voice the way a director talks to an actor, in plain English.

Instead of hunting through sliders to make a text-to-speech voice sound right, you
just tell Cue what you want, like *"warmer, slower, lean on this word"* or *"build
from calm to furious"*, and it works out the settings and delivery. You direct; the
voice performs.

```
Script:     It is okay.            Direction: build from calm to furious
            I said it is okay.
            Stop.                  →  It is okay.        [calm]      soothing
            STOP IT.                  I said it is okay. [serious]   firm, steady
                                      Stop.              [angry]     firm warning
                                      STOP IT.           [shouting]  furious
```

One direction restyles the whole script, and because the interpreter reads the
*entire* script, the emotion ramps line by line instead of hitting every line the
same.

## How it works

Cue has two halves with a clean seam between them: a **brain** that turns a
plain-English direction into a performance, and a **voice** that performs it.

**Brain (direction → performance).** A language model reads the script and your
direction and returns, for each line, a set of expressive settings plus inline
[ElevenLabs v3 audio tags](https://elevenlabs.io) (`[sarcastic]`, `[whispers]`,
`[urgent]`…). The tags are what make the voice *act*, not just change pace. The
brain tries a fast cloud model first and degrades gracefully:

```
GroqBrain (cloud, ~0.5s)  →  OllamaBrain (local, offline)  →  KeywordBrain (deterministic)
```

Every model's answer is run through a validator that clamps bad values and drops
any tag outside an allow-list, so a hallucinated number can never reach the voice.

**Voice (performance → audio).** The chosen settings and tags are sent to a voice
provider, which is also a fallback chain:

```
ElevenLabs v3 (studio quality)  →  Piper (local, offline)
```

Renders are cached on disk, content-addressed by everything that affects the
audio (voice, settings, tags, text). An identical line is never re-generated,
which is what keeps the project inside the free ElevenLabs quota.

## Stack

- **Backend**: Python 3.11, FastAPI. Endpoints: `/direct` (interpret a whole
  script), `/render` (voice one line), `/voices`, `/audio`.
- **Frontend**: Next.js (App Router, TypeScript, Tailwind). A script editor with
  a voice picker and a card per line.
- **Voice**: ElevenLabs `eleven_v3` (cloud) with Piper (local) as the offline /
  out-of-quota fallback.
- **Brain**: Groq (cloud) with a local Ollama model as the fallback.

Pure-logic modules are built test-first; the suite covers the cache, the engine,
the brain orchestration, the settings/tag validators, and the script parsing.

## Running it

**Backend**

```bash
cd backend
python3.11 -m venv venv
venv/bin/pip install -r requirements.txt
cp .env.example .env        # then paste your ElevenLabs + Groq keys
venv/bin/uvicorn main:app --reload
```

Both keys are optional; without them Cue falls back to the local Piper voice and
the keyword/Ollama brain. See `backend/requirements.txt` for the one-time Piper
voice download and the optional Ollama setup.

**Frontend**

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

The interactive API docs are at `http://localhost:8000/docs`.

## Bring your own key

Visitors can paste their own ElevenLabs API key in the studio ("Use your key"),
so their reads spend their credits and the voice pickers list their account's
voices, clones included.

Where the key travels, exactly:

- It lives in your browser only. Session storage by default (gone when the tab
  closes); local storage only if you tick "remember on this device".
- It rides your own requests as an `X-ElevenLabs-Key` header, exists in server
  memory just long enough to be forwarded to ElevenLabs, and is then gone.
- It is never written to disk, never logged, and never echoed back: error
  responses are deliberately generic, and tests pin that down (`test_byok.py`).
- Cached audio is keyed by content, never by key, so nothing about your account
  is derivable from the cache.

If you host Cue anywhere beyond localhost, put it behind HTTPS; the header is
only as private as the transport. And since ElevenLabs' API allows browser
cross-origin calls, a future zero-trust mode could send the key straight from
the browser to ElevenLabs without it ever touching this server.

## Notes

- ElevenLabs' free tier gives 10,000 credits per month and blocks shared *library*
  voices via the API, so the voice picker only lists voices the free tier can
  actually render.
- Built in steps, each one working before the next; see `CueBuildPlan.md`.

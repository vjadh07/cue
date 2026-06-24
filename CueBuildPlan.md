# Cue — Build Plan

The whole idea here is to build this in chunks where each chunk actually works before I move on to the next one. That way I'm never sitting on a pile of half-finished code, and I understand every piece because I built it and tested it myself.

Cue is a voice-direction tool. Instead of fiddling with sliders to make an AI voice sound a certain way, you just tell it what you want in plain English — "warmer, slower, lean on this word" — and it figures out the settings. You direct it like a director talks to an actor.

---

## Step 1 — Get the bones working

Set up the Python backend and the Next.js frontend and connect them. Get it so I can type a line and hear it read out loud using the browser's built-in voice. No AI yet, no fancy voice yet. This step is just proving the basic plumbing runs end to end.

Done when: I type a line, hit play, and hear it.

## Step 2 — The direction part

Now I type something like "say it warm and slow" and the system turns that plain-English note into the actual settings a voice engine needs. This is the core idea of the whole project.

Done when: changing the direction visibly changes how the line is set up to be read.

## Step 3 — Real voice + caching

Swap the basic browser voice for the real ElevenLabs voice, which sounds way better. Then add caching so if I fix one line, it only redoes that one line instead of re-rendering the whole script. Saves time and money.

Done when: the voice sounds studio-quality, and re-directing one line leaves the rest untouched.

## Step 4 — The smart part

Up to now I direct one line at a time. This step lets me give one big instruction like "make the whole thing sound like a movie trailer" and the system works out everything that needs to change across all the lines and applies it.

Done when: one sentence restyles the entire script.

## Step 5 — Stitch it together

Join all the separate lines into one continuous track, with real pauses and proper timing, so it plays like a single recording instead of a bunch of clips glued together.

Done when: a multi-line script plays as one smooth, correctly-timed read.

## Step 6 — Music and polish

Add background music that automatically gets quieter when someone's talking, then clean up the overall volume so the final thing sounds finished and produced, not raw.

Done when: the output sounds like something you'd actually publish.

## Step 7 — Export

Bundle the whole project into one downloadable audio file.

Done when: full project goes in, one clean audio file comes out.

## Step 8 — Harden it

Multiple voices for different characters. Error handling. Retries when the voice service hiccups. Making sure it doesn't fall apart if someone uses it in a weird way.

Done when: I could hand it to a stranger and it wouldn't break.

## Step 9 — The pitch

This week isn't building. It's a short page explaining how Cue works, a quick screen recording of me actually using it to direct a real read line by line, and the email to ElevenLabs.

Done when: it's shipped and sent.

---

## Rules I'm building by

- One step at a time. Don't move on until the current step actually works.
- I understand every piece before moving on. If I can't explain it, we're not done.
- No giant code dumps. Build small, test, then continue.
- This goes on my resume, so I have to be able to defend every part of it in an interview.

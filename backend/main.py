"""Cue backend — Step 1.

A tiny FastAPI server. Its only job right now is to prove the pipe between
the frontend and the backend works: the frontend sends a line of text, this
server receives it and sends a confirmation back. The actual speaking happens
in the browser for now. In Step 3, this same endpoint is where real audio
(from ElevenLabs) will come back instead.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# The application object. Everything attaches to this.
app = FastAPI()

# The frontend runs on a different address (localhost:3000) than this backend
# (localhost:8000). Browsers block cross-address requests by default, so we
# explicitly allow the frontend to talk to us. This is CORS.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# Describes the shape of the data the frontend sends us: a JSON object with
# one field, "text". FastAPI uses this to validate incoming requests.
class SpeakRequest(BaseModel):
    text: str


# A simple health check. Visiting http://localhost:8000/ should return this,
# which is an easy way to confirm the server is alive.
@app.get("/")
def root():
    return {"status": "ok", "message": "Cue backend is running"}


# The main endpoint. The frontend POSTs a line here; we echo it back so the
# frontend knows the round trip succeeded, then it speaks the line.
@app.post("/speak")
def speak(request: SpeakRequest):
    return {"received": request.text}

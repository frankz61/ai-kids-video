"""Minimal ElevenLabs client (stdlib only). The key is read from the ELEVENLABS_API_KEY
environment variable (process, or the Windows user-level variable) and never written to disk.

  python eleven.py models
  python eleven.py voices
"""
import json
import os
import sys
import urllib.error
import urllib.request

API = "https://api.elevenlabs.io"


def api_key() -> str:
    key = os.environ.get("ELEVENLABS_API_KEY")
    if not key and os.name == "nt":
        import winreg
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as k:
                key = winreg.QueryValueEx(k, "ELEVENLABS_API_KEY")[0]
        except OSError:
            key = None
    if not key:
        raise SystemExit("ELEVENLABS_API_KEY is not set")
    return key


def call(path: str, payload: dict | None = None, timeout: int = 120) -> bytes:
    req = urllib.request.Request(
        API + path,
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={"xi-api-key": api_key(), "Content-Type": "application/json", "User-Agent": "tts-client/1.0"},
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.read()
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"ElevenLabs HTTP {e.code} on {path.split('?')[0]}: {e.read().decode('utf-8', 'replace')[:800]}") from None


def tts(text: str, voice_id: str, model_id: str, settings: dict | None = None, fmt: str = "mp3_44100_128", **extra) -> bytes:
    body = {"text": text, "model_id": model_id, **extra}
    if settings:
        body["voice_settings"] = settings
    return call(f"/v1/text-to-speech/{voice_id}?output_format={fmt}", body)


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "models"
    if cmd == "models":
        for m in json.loads(call("/v1/models")):
            print(f"{m['model_id']:28s} tts={m.get('can_do_text_to_speech')} style={m.get('can_use_style')} "
                  f"maxchars={m.get('maximum_text_length_per_request')}  {m.get('name')}")
    elif cmd == "voices":
        for v in json.loads(call("/v1/voices"))["voices"]:
            lb = v.get("labels") or {}
            print(f"{v['voice_id']}  {v['name'][:34]:34s} {v.get('category', ''):10s} "
                  f"{lb.get('gender', ''):7s} {lb.get('age', ''):11s} {lb.get('accent', ''):10s} {lb.get('descriptive', lb.get('description', ''))} / {lb.get('use_case', '')}")
    elif cmd == "user":
        s = json.loads(call("/v1/user/subscription"))
        print({k: s.get(k) for k in ("tier", "character_count", "character_limit", "status")})

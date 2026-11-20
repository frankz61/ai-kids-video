"""Does H3 talk in its shots? Transcribe the native audio of every H3 clip and flag the ones with speech.

  python tools/h3_voice_check.py episodes/s02e*            # the clips as H3 made them (h3/clips_1080p, else h3/clips)
  python tools/h3_voice_check.py episodes/s02e* --amb      # after tools/strip_h3_voices.sh: is h3/amb/ clean now?
  options: --model small|medium|large-v3 (default small)  --device cpu|cuda (default cpu)  --json report.json

H3 is asked for "no speech", but it still mumbles English babble, Chinese or made-up words now and then. The characters'
lines come from TTS, so the clip audio must only be ambience. A flagged shot goes through tools/strip_h3_voices.sh.

Flag rules: a segment is speech when Whisper's no_speech_prob < 0.5 and its text is not a known Whisper hallucination on
music or room tone ("Thank you for watching", "Subtitles by ..."), and, when Whisper cannot tell the language
(probability < 0.5), it has at least three words. The language Whisper detects is printed too: zh in an
English show is always wrong. With --amb it also prints the loudness of the ambience and of the removed vocals.

Needs: pip install faster-whisper (and numpy, scipy for --amb), ffmpeg.
Windows notes: the CUDA build needs cuBLAS 12 DLLs; without them use --device cpu (small model: ~3 s a clip).
A half-downloaded model in the Hugging Face cache hangs the load: delete it, or set HF_HUB_OFFLINE=1 for a model you have.
Set PYTHONIOENCODING=utf-8 on a GBK console.
"""
import argparse
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

HALLUCINATIONS = re.compile(r"thank(s| you) for watching|subscribe|subtitles? by|amara\.org|字幕|请不吝|点赞|订阅", re.I)


def clips(ep, amb):
    if amb:
        return sorted((ep / "h3" / "amb").glob("shot_??.wav"))
    d = ep / "h3" / "clips_1080p"
    return sorted((d if d.exists() else ep / "h3" / "clips").glob("shot_*.mp4"))


def db(path):
    import numpy as np
    from scipy.io import wavfile
    a = wavfile.read(path)[1].astype("float32") / 32768
    return round(float(20 * np.log10(np.sqrt(np.mean(a ** 2)) + 1e-9)), 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("episodes", nargs="+")
    ap.add_argument("--amb", action="store_true")
    ap.add_argument("--model", default="small")
    ap.add_argument("--device", default="cpu")
    ap.add_argument("--json")
    a = ap.parse_args()
    from faster_whisper import WhisperModel
    model = WhisperModel(a.model, device=a.device, compute_type="int8" if a.device == "cpu" else "int8_float16")
    tmp = Path(tempfile.mkdtemp(prefix="h3voice_"))
    report, flagged = {}, []
    for ep in sorted({Path(p) for p in a.episodes if Path(p).is_dir()}):
        for c in clips(ep, a.amb):
            key = f"{ep.name}/{c.stem}"
            wav = tmp / (key.replace("/", "__") + ".wav")
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(c), "-vn", "-ac", "1", "-ar", "16000", str(wav)], check=True)
            segs, info = model.transcribe(str(wav), beam_size=5, condition_on_previous_text=False)
            segs = [(round(s.start, 1), round(s.end, 1), s.text.strip(), round(s.no_speech_prob, 2)) for s in segs]
            sure = info.language_probability >= 0.5     # a lone word in an unknown language is Whisper guessing at noise
            speech = [s for s in segs if s[3] < 0.5 and s[2] and not HALLUCINATIONS.search(s[2])
                      and (sure or len(s[2].split()) >= 3)]
            r = {"lang": info.language, "p": round(info.language_probability, 2), "segments": segs, "speech": bool(speech)}
            if a.amb:
                v = c.with_name(c.stem + "_removed_vocals.wav")
                r["amb_db"], r["removed_db"] = db(c), (db(v) if v.exists() else None)
            report[key] = r
            if speech:
                flagged.append(key)
            text = " / ".join(s[2] for s in speech) or "-"
            extra = f"  amb {r['amb_db']} dB, removed {r['removed_db']} dB" if a.amb else ""
            print(f"{'SPEECH' if speech else 'ok    '} {key:28s} {info.language} {info.language_probability:.2f}  {text}{extra}", flush=True)
    print(f"\n{len(flagged)} of {len(report)} shots have speech" + (": " + " ".join(flagged) if flagged else ""))
    if a.json:
        Path(a.json).write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    sys.exit(1 if flagged else 0)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    main()

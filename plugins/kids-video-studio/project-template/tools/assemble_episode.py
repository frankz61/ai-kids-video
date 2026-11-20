"""Assemble one episode at 1080p from its episode.json: H5 segments + H3 clips + voice + music -> final mp4.

Usage: python tools/assemble_episode.py <episode_dir>
Needs: <ep>/build/h5/<segment>.mp4 + timeline.json (capture.mjs --scale 1.5), <ep>/audio/tts/*.wav,
       H3 clips at 1920x1080 (default <ep>/h3/clips_1080p/shot_NN.mp4, or a path given in the order entry).
Writes <ep>/output/<output_name>.mp4, <output_name>_nosub.mp4, <output_name>.srt.

Audio is built as ONE PCM track in numpy (each line placed at its exact sample) and encoded once:
per-segment AAC + concat drifts at the seams, and ffmpeg's amix filter can deadlock intermittently.
"""
import json
import os
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
from season_lib import ROOT, SR, load_episode, read_wav, run, write_wav  # noqa: E402

FPS, VW, VH = 24, 1920, 1080
H3_LEN = 5.0
FONTS_DIR = ROOT / "assets" / "fonts"   # static bold cut of Noto Sans SC (tools/make_sub_font.py)
AI_LABEL = "内容由AI生成"                # China's AI-content labelling rules require a visible mark
VOICE_CREDIT = "ElevenLabs"


def make_music(path, seconds, bpm=104):
    """Gentle marimba-style loop (C - Am - F - G), fully synthesized, so no music licensing questions."""
    n = int(seconds * SR) + SR
    out = np.zeros(n, dtype=np.float64)
    beat = 60.0 / bpm

    def note(freq, t0, length=0.9, amp=0.5):
        i0 = int(t0 * SR)
        m = min(int(length * SR), n - i0)
        if m <= 0:
            return
        t = np.arange(m) / SR
        tone = np.sin(2 * np.pi * freq * t) + 0.35 * np.sin(2 * np.pi * 2 * freq * t) * np.exp(-t * 9) \
            + 0.12 * np.sin(2 * np.pi * 4 * freq * t) * np.exp(-t * 20)
        out[i0:i0 + m] += amp * tone * np.exp(-t * 5.5) * np.minimum(1, t * 400)

    f = lambda semis: 261.63 * 2 ** (semis / 12)  # noqa: E731
    chords = [(0, 4, 7), (-3, 0, 4), (-7, -3, 0), (-5, -1, 2)]
    melody = [[12, None, 7, 4, 7, None, 12, None], [9, None, 4, 0, 4, None, 9, None],
              [5, None, 9, 12, 9, None, 5, None], [7, None, 11, 14, 11, 7, 2, None]]
    bar, t = 0, 0.0
    while t < seconds:
        root, third, fifth = chords[bar % 4]
        for b in range(4):
            note(f(root - 12), t + b * beat, 0.8, 0.42 if b % 2 == 0 else 0.25)
            note(f(third), t + (b + 0.5) * beat, 0.5, 0.16)
            note(f(fifth), t + (b + 0.5) * beat, 0.5, 0.16)
        for i, s in enumerate(melody[bar % 4]):
            if s is not None:
                note(f(s), t + i * beat / 2, 0.7, 0.30)
        t += 4 * beat
        bar += 1
    out = out[: int(seconds * SR)]
    out = out / np.max(np.abs(out)) * 0.8
    write_wav(path, np.stack([out, out], axis=1))


AMB_RMS_DB = -34.0    # H3 ambience bed level (voice lines sit around -16 LUFS), same for every clip
AMB_SOLO_RMS_DB = -26.0  # shots with no voice line: the ambience carries the moment, so it sits higher
AMB_DUCK = 0.45       # ambience gain while a voice line plays
AMB_MAX_GAIN_DB = 18.0


VOICE_RMS_DB = -17.0  # every voice line is brought to the same active-speech RMS (TTS lines were only peak-normalised)


def level_voice(x):
    """Loudness-match a voice line: RMS over the voiced samples to VOICE_RMS_DB, never letting peaks pass -0.5 dBFS."""
    x = x.astype(np.float32)
    active = x[np.abs(x).max(1) > 0.02]
    if len(active) == 0:
        return x
    rms, peak = float(np.sqrt(np.mean(active ** 2))), float(np.abs(x).max())
    return x * min(10 ** (VOICE_RMS_DB / 20) / rms, 0.944 / peak)


def level_ambience(a, spans):
    """Bring a clip's native ambience to one fixed level (so H3 shots match H5 scenes), duck it under voice, fade the ends."""
    a = a.astype(np.float32)
    rms = float(np.sqrt(np.mean(a ** 2))) if len(a) else 0.0
    if rms < 1e-5:
        return a * 0
    target = AMB_RMS_DB if spans else AMB_SOLO_RMS_DB
    gain = min(10 ** ((target - 20 * np.log10(rms)) / 20), 10 ** (AMB_MAX_GAIN_DB / 20))
    a = a * gain
    env = np.ones(len(a), np.float32)
    ramp = int(0.15 * SR)
    for s, e in spans:
        i, j = max(0, int(s * SR) - ramp), min(len(a), int(e * SR) + ramp)
        if i >= j:
            continue
        seg = np.full(j - i, AMB_DUCK, np.float32)
        k = min(ramp, (j - i) // 2)
        seg[:k] = np.linspace(1, AMB_DUCK, k)
        seg[len(seg) - k:] = np.linspace(AMB_DUCK, 1, k)
        env[i:j] = np.minimum(env[i:j], seg)
    f = min(int(0.08 * SR), len(a) // 2)
    env[:f] *= np.linspace(0, 1, f)
    env[len(env) - f:] *= np.linspace(1, 0, f)
    return np.clip(a * env[:, None], -0.5, 0.5)


def main():
    ep = Path(sys.argv[1]).resolve()
    spec = load_episode(ep)
    lines = spec["lines"]
    build, tts, out_dir = ep / "build", ep / "audio" / "tts", ep / "output"
    seg_dir = build / "segments"
    seg_dir.mkdir(parents=True, exist_ok=True)
    out_dir.mkdir(exist_ok=True)
    timeline = json.loads((build / "h5" / "timeline.json").read_text(encoding="utf-8"))
    durs = json.loads((ep / "audio" / "durations.json").read_text(encoding="utf-8"))
    name = spec["output_name"]

    def mix_cues(base, cues):
        for key, start in cues:
            x = level_voice(read_wav(tts / f"{key}.wav"))
            i = round(start * SR)
            n = max(0, min(len(x), len(base) - i))
            base[i:i + n] += x[:n]
        return base

    enc = ["-c:v", "libx264", "-crf", "17", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", str(FPS)]
    files, total, subs, seg_at = [], 0.0, [], {}
    for n, item in enumerate(spec["order"]):
        out = seg_dir / f"{n:02d}_{item[0]}_{item[1]}.mp4"
        if item[0] == "h5":
            seg = timeline[item[1]]
            dur, cues = seg["dur"], [(c["key"], c["start"]) for c in seg["cues"]]
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", build / "h5" / f"{item[1]}.mp4", "-an",
                 "-vf", f"scale={VW}:{VH},format=yuv420p", *enc, "-frames:v", round(dur * FPS), out])
            write_wav(out.with_suffix(".wav"), mix_cues(np.zeros((round(dur * SR), 2), np.float32), cues))
        else:
            dur, cues = H3_LEN, [tuple(c) for c in item[2]]
            clip = (ep / item[3]).resolve() if len(item) > 3 else ep / "h3" / "clips_1080p" / f"shot_{item[1]:02d}.mp4"
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", clip, "-an",
                 "-vf", f"scale={VW}:{VH}:force_original_aspect_ratio=increase,crop={VW}:{VH},fps={FPS},format=yuv420p",
                 *enc, "-frames:v", round(dur * FPS), out])
            amb = out.with_name(out.stem + "_amb.wav")   # the clip's own native ambience
            # H3 sometimes talks although asked not to: tools/strip_h3_voices.sh keeps only the non-vocal part (h3/amb/)
            clean = ep / "h3" / "amb" / f"shot_{item[1]:02d}.wav"
            src = clean if len(item) <= 3 and clean.exists() else clip
            run(["ffmpeg", "-y", "-loglevel", "error", "-i", src, "-vn", "-af", f"aresample={SR}",
                 "-ar", SR, "-ac", "2", "-c:a", "pcm_s16le", amb])
            base = np.zeros((round(dur * SR), 2), np.float32)
            a = read_wav(amb)[: len(base)]
            base[: len(a)] = level_ambience(a, [(s, s + durs[k]["dur"]) for k, s in cues])
            write_wav(out.with_suffix(".wav"), mix_cues(base, cues))
        for key, start in cues:
            subs.append([total + start, total + start + durs[key]["dur"] + 0.45, durs[key]["text"], lines[key].get("zh", "")])
        files.append((out, dur))
        seg_at.setdefault(str(item[1]), (total, total + dur))
        print(f"{out.name:28s} {dur:6.2f}s  @ {total:6.2f}", flush=True)
        total += dur

    # video: frame-exact concat
    lst = build / "concat.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p, _ in files), encoding="utf-8")
    body = build / "body.mp4"
    run(["ffmpeg", "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", lst, "-c", "copy", "-an", body])

    # audio: one continuous PCM track
    n_total = round(total * SR)
    voice = np.zeros((n_total, 2), dtype=np.float32)
    cum = 0.0
    for p, dur in files:
        start, end = round(cum * SR), round((cum + dur) * SR)
        seg = read_wav(p.with_suffix(".wav"))[: end - start]
        voice[start:start + len(seg)] += seg
        cum += dur
    make_music(build / "music.wav", total)
    music = read_wav(build / "music.wav")[:n_total] * 0.10
    t = np.arange(len(music)) / SR
    music *= (np.minimum(1, t / 1.0) * np.minimum(1, np.maximum(0, (total - t) / 1.2)))[:, None]
    voice[: len(music)] += music
    write_wav(build / "mix.wav", voice)
    norm_path = build / "mix_norm.wav"
    run(["ffmpeg", "-y", "-loglevel", "error", "-i", build / "mix.wav", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11",
         "-ar", SR, "-ac", "2", "-c:a", "pcm_s16le", norm_path])
    norm = read_wav(norm_path)
    fixed = np.zeros((n_total, 2), dtype=np.float32)
    fixed[: min(n_total, len(norm))] = norm[:n_total]
    write_wav(norm_path, fixed)

    # subtitles (ASS coordinates are 1280x720; libass scales them to 1080p)
    for a, b in zip(subs, subs[1:]):
        a[1] = min(a[1], b[0] - 0.04)

    def ts(x, sep, digits):
        h, m, s = int(x // 3600), int(x % 3600 // 60), x % 60
        return f"{h:d}:{m:02d}:{s:0{3 + digits}.{digits}f}".replace(".", sep)

    head = ["[Script Info]", "ScriptType: v4.00+", "PlayResX: 1280", "PlayResY: 720", "WrapStyle: 2", "ScaledBorderAndShadow: yes", "",
            "[V4+ Styles]",
            "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, "
            "StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding",
            "Style: Sub,Kids Sub Sans,40,&H00FFFFFF,&H00FFFFFF,&H00303030,&H80000000,-1,0,0,0,100,100,0,0,1,3.5,1,2,40,40,22,1",
            "Style: Mark,Kids Sub Sans,26,&H20FFFFFF,&H20FFFFFF,&H30303030,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,7,22,22,16,1",
            "Style: Credit,Kids Sub Sans,24,&H10FFFFFF,&H10FFFFFF,&H30303030,&H80000000,-1,0,0,0,100,100,0,0,1,2,0,9,22,22,16,1",
            "", "[Events]", "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text"]
    credits = f"Video: MiniMax H3 · Qwen-Image　Voice: {spec.get('credits_voice', VOICE_CREDIT)}"
    label = head + [f"Dialogue: 0,{ts(0, '.', 2)},{ts(total, '.', 2)},Mark,,0,0,0,,{AI_LABEL}",
                    f"Dialogue: 0,{ts(total - 4.6, '.', 2)},{ts(total, '.', 2)},Credit,,0,0,0,,{credits}"]
    for note in spec.get("notes", []):   # on-screen Chinese hints shown over given segments (e.g. safety tips)
        segs = [seg_at[s] for s in note["segments"] if s in seg_at]
        if segs:
            a, b = min(x[0] for x in segs), max(x[1] for x in segs)
            label.append(f"Dialogue: 0,{ts(a, '.', 2)},{ts(b, '.', 2)},Credit,,0,0,0,,{{\\an8\\pos(640,64)\\fs28}}{note['text']}")
    if spec.get("parent_note"):   # Chinese note for parents, top centre over the outro (e.g. the family episode)
        label.append(f"Dialogue: 0,{ts(total - 4.6, '.', 2)},{ts(total, '.', 2)},Credit,,0,0,0,,"
                     f"{{\\an8\\pos(640,64)\\fs30}}给家长：{spec['parent_note']}")
    ass, srt = list(head), []
    for i, (a, b, en, zh) in enumerate(subs, 1):
        ass.append(f"Dialogue: 0,{ts(a, '.', 2)},{ts(b, '.', 2)},Sub,,0,0,0,,{{\\fs46}}{en}" + (f"\\N{{\\fs34}}{zh}" if zh else ""))
        srt.append(f"{i}\n{'0' + ts(a, ',', 3)} --> {'0' + ts(b, ',', 3)}\n{en}\n{zh}\n")
    (build / "label.ass").write_text("\n".join(label) + "\n", encoding="utf-8")
    (build / "subs.ass").write_text("\n".join(ass) + "\n", encoding="utf-8")
    (out_dir / f"{name}.srt").write_text("\n".join(srt), encoding="utf-8")

    fonts = os.path.relpath(FONTS_DIR, build).replace("\\", "/")
    fade = f"fade=t=in:st=0:d=0.4,fade=t=out:st={total - 0.6:.2f}:d=0.6,subtitles=label.ass:fontsdir={fonts}"
    for fname, vf in ((f"{name}.mp4", fade + f",subtitles=subs.ass:fontsdir={fonts}"), (f"{name}_nosub.mp4", fade)):
        run(["ffmpeg", "-y", "-loglevel", "error", "-i", body, "-i", norm_path, "-vf", vf, "-map", "0:v", "-map", "1:a",
             "-c:v", "libx264", "-crf", "18", "-preset", "medium", "-pix_fmt", "yuv420p", "-r", FPS,
             "-c:a", "aac", "-b:a", "192k", "-ar", SR, "-movflags", "+faststart",
             "-metadata", f"comment=AI-generated content (video: MiniMax H3, Qwen-Image; voice: {spec.get('credits_voice', VOICE_CREDIT)})",
             out_dir / fname], cwd=build)
        print(f"FINAL {out_dir / fname}  {total:.2f}s  {len(subs)} subtitle cues", flush=True)


if __name__ == "__main__":
    main()

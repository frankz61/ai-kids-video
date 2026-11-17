"""Runs ON the Colab VM inside one engine's venv:  python gen_tts.py <engine> [key ...]

Reads /content/tts/lines.json ({key: {"role": "narrator"|"hero", "text": "[tag] words"}}) and writes
/content/tts/out/<engine>/<key>.wav (mono, native sample rate). Each line gets up to 4 takes; the first take
whose length is plausible for the text is kept (models can ramble or truncate on very short inputs).
"""
import json
import re
import sys
import time
from pathlib import Path

import numpy as np
import soundfile as sf
import torch

ROOT = Path("/content/tts")
ENGINE = sys.argv[1]
ONLY = set(sys.argv[2:])
LINES = json.loads((ROOT / "lines.json").read_text())
OUT = ROOT / "out" / ENGINE
OUT.mkdir(parents=True, exist_ok=True)
REF = ROOT / "ref"  # reference clips for engines that clone a voice (made from Kokoro output)

TAG = re.compile(r"\[([^\]]*)\]\s*")
HIGH = {"excited", "amazed", "gasps"}  # tags that call for a bigger delivery


def spoken(text):
    return TAG.sub("", text).strip()


def tags(text):
    return {t.strip() for m in TAG.findall(text) for t in m.split(",")}


def voiced_seconds(x, sr):
    """Length between the first and last sample above -40 dBFS (ignores leading/trailing silence)."""
    a = np.abs(x)
    idx = np.where(a > max(0.02 * a.max(), 1e-4))[0]
    return 0.0 if len(idx) == 0 else (idx[-1] - idx[0]) / sr


def plausible(x, sr, text):
    d = voiced_seconds(x, sr)
    n = len(spoken(text))
    return 0.25 <= d <= 1.0 + 0.2 * n, d


# ---------------- engines: each returns (float32 mono array, sample_rate) ----------------
def load_kokoro():
    from kokoro import KPipeline
    pipe = KPipeline(lang_code="a", repo_id="hexgrad/Kokoro-82M")
    voices = {"narrator": "af_heart", "hero": "af_bella"}

    def gen(text, role, seed):
        chunks = [a for _, _, a in pipe(spoken(text), voice=voices[role], speed=1.0)]
        return np.concatenate([np.asarray(c, dtype=np.float32) for c in chunks]), 24000
    return gen


def load_chatterbox():
    from chatterbox.tts import ChatterboxTTS
    model = ChatterboxTTS.from_pretrained(device="cuda")

    def gen(text, role, seed):
        torch.manual_seed(seed)
        ex = 0.75 if tags(text) & HIGH else 0.6  # emotion exaggeration; lower cfg keeps the pace natural
        wav = model.generate(spoken(text), exaggeration=ex, cfg_weight=0.35)
        return wav.squeeze(0).float().cpu().numpy(), model.sr
    return gen


def load_orpheus():
    from snac import SNAC
    from transformers import AutoModelForCausalLM, AutoTokenizer
    name = "unsloth/orpheus-3b-0.1-ft"  # ungated mirror of canopylabs/orpheus-3b-0.1-ft
    tok = AutoTokenizer.from_pretrained(name)
    model = AutoModelForCausalLM.from_pretrained(name, torch_dtype=torch.bfloat16).cuda().eval()
    snac = SNAC.from_pretrained("hubertsiuzdak/snac_24khz").cuda().eval()
    voices = {"narrator": "tara", "hero": "mia"}
    native = {"gasps": "<gasp>", "giggles": "<giggle>", "laughs": "<laugh>", "sighs": "<sigh>"}

    def gen(text, role, seed):
        torch.manual_seed(seed)
        prefix = "".join(native[t] + " " for t in tags(text) if t in native)
        ids = tok(f"{voices[role]}: {prefix}{spoken(text)}", return_tensors="pt").input_ids
        ids = torch.cat([torch.tensor([[128259]]), ids, torch.tensor([[128009, 128260]])], dim=1).cuda()
        with torch.no_grad():
            out = model.generate(input_ids=ids, attention_mask=torch.ones_like(ids), max_new_tokens=1400,
                                 do_sample=True, temperature=0.6, top_p=0.95, repetition_penalty=1.1,
                                 eos_token_id=128258)
        row = out[0]
        starts = (row == 128257).nonzero()
        row = row[starts[-1].item() + 1:] if len(starts) else row
        row = row[row != 128258]
        row = row[: len(row) // 7 * 7].tolist()
        codes = [t - 128266 for t in row]
        l1, l2, l3 = [], [], []
        for i in range(len(codes) // 7):
            c = codes[7 * i: 7 * i + 7]
            l1.append(c[0]); l2.append(c[1] - 4096); l3 += [c[2] - 2 * 4096, c[3] - 3 * 4096]
            l2.append(c[4] - 4 * 4096); l3 += [c[5] - 5 * 4096, c[6] - 6 * 4096]
        if not l1:
            return np.zeros(2400, dtype=np.float32), 24000
        layers = [torch.tensor(x, device="cuda").unsqueeze(0) for x in (l1, l2, l3)]
        with torch.no_grad():
            audio = snac.decode(layers)
        return audio.squeeze().float().cpu().numpy(), 24000
    return gen


def load_dia():
    from dia.model import Dia
    model = Dia.from_pretrained("nari-labs/Dia-1.6B-0626", compute_dtype="float16")
    # Dia picks a random voice per call unless given a reference clip + its transcript to continue from.
    refs = {r: (str(REF / f"{r}.wav"), (REF / f"{r}.txt").read_text().strip()) for r in ("narrator", "hero")}
    non_verbal = {"gasps": "(gasps)", "giggles": "(giggles)", "laughs": "(laughs)"}

    def gen(text, role, seed):
        torch.manual_seed(seed)
        ref_wav, ref_txt = refs[role]
        nv = "".join(non_verbal[t] + " " for t in tags(text) if t in non_verbal)
        out = model.generate(f"[S1] {ref_txt} [S1] {nv}{spoken(text)}", audio_prompt=ref_wav,
                             use_torch_compile=False, verbose=False, cfg_scale=3.0, temperature=1.3, top_p=0.9)
        return np.asarray(out, dtype=np.float32), 44100
    return gen


LOADERS = {"kokoro": load_kokoro, "chatterbox": load_chatterbox, "orpheus": load_orpheus, "dia": load_dia}

REF_TEXT = {  # one longer sentence per role, so Dia has 4-6 s of a stable voice to continue from
    "narrator": "Hello, friends! Today we are going to play a fun game with colors. Are you ready? Let's go!",
    "hero": "Hi there! I'm a little fox, and I love to run and jump and play with my friends!",
}


def make_refs():
    import subprocess
    gen = load_kokoro()
    REF.mkdir(exist_ok=True)
    for role, text in REF_TEXT.items():
        x, sr = gen(text, role, 0)
        sf.write(REF / f"{role}_24k.wav", x, sr)
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(REF / f"{role}_24k.wav"),
                        "-ar", "44100", str(REF / f"{role}.wav")], check=True)
        (REF / f"{role}.txt").write_text(text)
        print(f"  ref {role}: {len(x) / sr:.1f}s", flush=True)


def main():
    if ENGINE == "refs":
        make_refs()
        return
    t0 = time.time()
    gen = LOADERS[ENGINE]()
    print(f"[{ENGINE}] model loaded in {time.time() - t0:.0f}s", flush=True)
    report = {}
    for i, (key, line) in enumerate(LINES.items()):
        if ONLY and key not in ONLY:
            continue
        best = None
        for take in range(4):
            x, sr = gen(line["text"], line["role"], seed=1000 + 97 * i + take)
            ok, d = plausible(x, sr, line["text"])
            if best is None or ok:
                best = (x, sr, d, take)
            if ok:
                break
        x, sr, d, take = best
        sf.write(OUT / f"{key}.wav", x, sr)
        report[key] = {"voiced_s": round(d, 2), "take": take, "ok": bool(plausible(x, sr, line["text"])[0])}
        print(f"  {key:16s} {d:5.2f}s take={take} {'ok' if report[key]['ok'] else 'SUSPECT'}  {spoken(line['text'])}",
              flush=True)
    (OUT / "_report.json").write_text(json.dumps(report, indent=1))
    print(f"[{ENGINE}] done in {time.time() - t0:.0f}s", flush=True)


if __name__ == "__main__":
    main()

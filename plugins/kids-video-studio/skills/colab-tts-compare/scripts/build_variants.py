"""Build one comparison video per open-source voice from the Colab output archive.

Usage: python build_variants.py <episode_dir> <out.tgz> [engine ...]
For each engine: unpack raw wavs -> import_variant (same post-processing as the main voice) ->
re-capture the H5 scenes with that voice's timings -> assemble (VOICE=<engine>) -> sync check.
Results: <episode>/output/compare/<name>_<engine>.mp4
"""
import os
import subprocess
import sys
import tarfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
TOOLS = HERE.parent
ep, tgz = Path(sys.argv[1]).resolve(), Path(sys.argv[2]).resolve()
raw_root = ep / "audio" / "variants" / "_raw"
with tarfile.open(tgz) as tf:
    tf.extractall(raw_root, filter="data")
available = sorted(p.name for p in (raw_root / "out").iterdir() if p.is_dir() and any(p.glob("*.wav")))
engines = sys.argv[3:] or available
print("engines with output:", available, "| building:", engines, flush=True)


def run(cmd, **kw):
    print("  $", " ".join(map(str, cmd))[:160], flush=True)
    r = subprocess.run(cmd, text=True, capture_output=True, stdin=subprocess.DEVNULL, timeout=1800, **kw)
    if r.returncode != 0:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise RuntimeError(f"failed: {cmd[:3]}")
    return r.stdout


results = {}
for e in engines:
    print(f"=== {e}", flush=True)
    try:
        print(run([sys.executable, str(HERE / "import_variant.py"), str(ep), e, str(raw_root / "out" / e)]).strip())
        build = ep / "build" / "variants" / e
        run(["node", "capture.mjs", str(ep / "h5" / "index.html"), str(build / "h5"), "--dur", f"durations_{e}.js"],
            cwd=TOOLS)
        out = run([sys.executable, str(ep / "assemble.py")], cwd=ep, env={**os.environ, "VOICE": e})
        print(out.strip().splitlines()[-1])
        name = next(ep.joinpath("output", "compare").glob(f"*_{e}.mp4"))
        lag = run([sys.executable, str(TOOLS / "audio_lag.py"), str(build / "mix_norm.wav"), str(name), "60"])
        bad = [ln for ln in lag.splitlines() if "lag" in ln and "+0 ms" not in ln]
        results[e] = f"{name.name}  sync {'OK' if not bad else 'OFF: ' + '; '.join(bad)}"
    except Exception as ex:  # noqa: BLE001  keep going with the other engines
        results[e] = f"FAILED: {ex}"
print("\n".join(f"{k:12s} {v}" for k, v in results.items()))

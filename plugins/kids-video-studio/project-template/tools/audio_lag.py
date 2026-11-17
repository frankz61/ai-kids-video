"""Lag of audio in file B relative to file A, per window. Usage: python audio_lag.py A B [window_s]"""
import subprocess
import sys

import numpy as np

SR = 8000


def pcm(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR), "-f", "s16le", "-"],
                         capture_output=True, check=True).stdout
    return np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768


a, b = pcm(sys.argv[1]), pcm(sys.argv[2])
win = float(sys.argv[3]) if len(sys.argv) > 3 else 15.0
hop = 40  # 5 ms envelope
env = lambda x: np.abs(x)[: len(x) // hop * hop].reshape(-1, hop).mean(1)  # noqa: E731
ea, eb = env(a), env(b)
n = int(win * SR / hop)
maxlag = int(2.0 * SR / hop)
print(f"len A={len(a) / SR:.2f}s  B={len(b) / SR:.2f}s")
for i in range(0, min(len(ea), len(eb)) - n, n):
    x = ea[i:i + n] - ea[i:i + n].mean()
    lo, hi = max(0, i - maxlag), min(len(eb), i + n + maxlag)
    y = eb[lo:hi] - eb[lo:hi].mean()
    c = np.correlate(y, x, mode="valid")
    lag = (lo + int(np.argmax(c)) - i) * hop / SR
    print(f"  {i * hop / SR:6.1f}s  lag {lag * 1000:+6.0f} ms   (peak {c.max() / (np.linalg.norm(x) * np.linalg.norm(y) + 1e-9):.2f})")

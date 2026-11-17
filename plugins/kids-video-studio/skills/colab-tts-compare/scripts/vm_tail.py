# Executed in the Colab kernel via `colab exec`: show the tail of the given logs (TAIL_FILES, space separated).
import os
from pathlib import Path

for f in os.environ.get("TAIL_FILES", "").split():
    p = Path(f)
    print(f"----- {f}")
    if p.exists():
        lines = p.read_text(errors="replace").splitlines()
        print("\n".join(lines[-int(os.environ.get("TAIL_N", "15")):]))
    else:
        print("(missing)")

# colab exec: pack selected engine outputs for download. PACK_ENGINES="chatterbox dia", PACK_NAME=xxx.tgz
import os
import subprocess

eng = " ".join(f"out/{e}" for e in os.environ["PACK_ENGINES"].split())
name = os.environ.get("PACK_NAME", "pack.tgz")
r = subprocess.run(f"cd /content/tts && tar czf {name} {eng} ref && ls -la {name}", shell=True,
                   capture_output=True, text=True)
print(r.stdout, r.stderr)

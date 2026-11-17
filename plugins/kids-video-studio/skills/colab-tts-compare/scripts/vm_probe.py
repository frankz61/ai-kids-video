import shutil
import subprocess
import sys

print("python", sys.version.split()[0])
for cmd in ("nvidia-smi --query-gpu=name,memory.total --format=csv,noheader", "df -h /content | tail -1",
            "free -g | head -2", "which uv espeak-ng ffmpeg git", "pip --version"):
    print("$", cmd)
    print(subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip())
print("uv:", shutil.which("uv"))

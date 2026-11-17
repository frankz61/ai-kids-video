# Executed in the Colab kernel via `colab exec`. Starts a shell command detached from the kernel so it
# survives the exec timeout. The command comes from the BG_CMD env var; output goes to BG_LOG.
import os
import subprocess

os.makedirs("/content/tts", exist_ok=True)
cmd, log = os.environ["BG_CMD"], os.environ["BG_LOG"]
p = subprocess.Popen(["bash", "-c", f"{cmd} > {log} 2>&1"], start_new_session=True, cwd="/content/tts")
print("started pid", p.pid, "->", log)

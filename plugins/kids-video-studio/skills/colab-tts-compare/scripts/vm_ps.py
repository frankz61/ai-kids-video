# colab exec: what is running on the VM right now
import subprocess

for cmd in ("date +%T", "ps -eo pid,etime,pcpu,rss,args --sort=-pcpu | grep -E 'gen_tts|run_all' | grep -v grep",
            "nvidia-smi --query-gpu=utilization.gpu,memory.used --format=csv,noheader",
            "ls -la --time-style=+%T /content/tts/out/dia | tail -4"):
    print("$", cmd)
    print(subprocess.run(cmd, shell=True, capture_output=True, text=True).stdout.strip())

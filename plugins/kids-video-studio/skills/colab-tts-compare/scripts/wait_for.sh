#!/usr/bin/env bash
# wait_for.sh <remote_marker_file> <max_minutes> [log files to tail when done...]
# Polls the Colab VM every 30 s until the marker exists (or a log line says *_DONE), then prints the logs.
W="$(cd "$(dirname "$0")" && pwd)"
marker="$1"; max="$2"; shift 2
logs="$*"
for ((i = 0; i < max * 2; i++)); do
  out=$(bash "$W/colab.sh" exec "$W/vm_tail.py" 60 "TAIL_FILES=$marker" "TAIL_N=3")
  if ! grep -q "(missing)" <<<"$out" && [ -n "$out" ]; then
    echo "marker present after ~$((i / 2)) min"
    [ -n "$logs" ] && bash "$W/colab.sh" exec "$W/vm_tail.py" 60 "TAIL_FILES=$logs" "TAIL_N=${TAIL_N:-6}"
    exit 0
  fi
  sleep 30
done
echo "TIMEOUT waiting for $marker"
[ -n "$logs" ] && bash "$W/colab.sh" exec "$W/vm_tail.py" 60 "TAIL_FILES=$logs" "TAIL_N=${TAIL_N:-6}"
exit 1

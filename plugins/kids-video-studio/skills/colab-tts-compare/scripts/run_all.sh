#!/usr/bin/env bash
# Runs ON the Colab VM after setup: generate every engine one after another (they share the GPU),
# then pack the results. A failing engine does not stop the others.
# Usage: bash run_all.sh [engine ...]     (default: all)
set -u
cd /content/tts
engines=("$@"); [ ${#engines[@]} -eq 0 ] && engines=(kokoro refs chatterbox orpheus dia)
for e in "${engines[@]}"; do
  venv="$e"; [ "$e" = refs ] && venv=kokoro
  echo "=== $e $(date +%T)"
  if /content/venv/$venv/bin/python -u gen_tts.py "$e" > "gen_$e.log" 2>&1; then
    echo "GEN_OK $e"
  else
    echo "GEN_FAIL $e"; tail -n 25 "gen_$e.log"
  fi
done
tar czf /content/tts/out.tgz -C /content/tts out ref
echo "ALL_DONE $(date +%T)"
touch /content/tts/gen.done

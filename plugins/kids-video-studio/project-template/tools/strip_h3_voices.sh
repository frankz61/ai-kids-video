#!/usr/bin/env bash
# H3 sometimes speaks in a shot (English babble, Chinese, made-up words) although the prompt says "no speech".
# The characters' lines come from TTS, so a clip's native audio should only be ambience. This splits the audio of the
# given episodes' H3 shots with Demucs (htdemucs, two stems) on a Colab GPU and keeps the non-vocal part as
# h3/amb/shot_NN.wav (plus shot_NN_removed_vocals.wav to listen to what was taken out). assemble_episode.py uses
# h3/amb/shot_NN.wav instead of the clip's own audio when it exists. Check the result: tools/h3_voice_check.py --amb
#
# Usage (Linux / WSL, a Colab session running, e.g. from the comfyui-h3-colab skill):
#   bash tools/strip_h3_voices.sh episodes/s02e01_bag episodes/s02e02_positions ...
# Env: COLAB_SESSION (default minimax-h3), COLAB_BIN (default: colab on PATH)
# Colab allows one SSH connection per session: stop keep_ssh_tunnel.sh first, or this fails with HTTP 429.
set -euo pipefail
COLAB=${COLAB_BIN:-colab}
S=${COLAB_SESSION:-minimax-h3}
[ $# -gt 0 ] || { echo "usage: $0 <episode dir> [...]"; exit 2; }
TMP=$(mktemp -d)
trap 'rm -rf "$TMP"' EXIT
ssh_colab() { ssh -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null -o ServerAliveInterval=20 \
  -o LogLevel=ERROR -o "ProxyCommand=$COLAB ssh --proxy-mode -s $S" root@colab "$@"; }

declare -A EPDIR
mkdir -p "$TMP/in"
for ep in "$@"; do
  ep=$(cd "$ep" && pwd); name=$(basename "$ep"); EPDIR[$name]=$ep
  src="$ep/h3/clips_1080p"; [ -d "$src" ] || src="$ep/h3/clips"
  for c in "$src"/shot_*.mp4; do
    ffmpeg -nostdin -y -loglevel error -i "$c" -vn -ac 2 -ar 44100 "$TMP/in/${name}__$(basename "${c%.mp4}").wav"
  done
done
tar -C "$TMP" -cf "$TMP/in.tar" in
"$COLAB" upload -s "$S" "$TMP/in.tar" /content/h3_amb_in.tar >/dev/null
ssh_colab 'set -e; cd /content; rm -rf h3amb; mkdir h3amb; tar -C h3amb -xf h3_amb_in.tar
  pip -q install demucs >/dev/null 2>&1
  python -m demucs --two-stems=vocals -n htdemucs -o h3amb/out h3amb/in/*.wav 2>&1 | tail -2
  cd h3amb/out/htdemucs && tar -cf /content/h3_amb_out.tar */no_vocals.wav */vocals.wav'
"$COLAB" download -s "$S" /content/h3_amb_out.tar "$TMP/out.tar" >/dev/null
mkdir -p "$TMP/out" && tar -C "$TMP/out" -xf "$TMP/out.tar"
n=0
for d in "$TMP"/out/*/; do
  k=$(basename "$d"); ep=${EPDIR[${k%%__*}]}; shot=${k##*__}
  mkdir -p "$ep/h3/amb"
  cp "$d/no_vocals.wav" "$ep/h3/amb/$shot.wav"
  cp "$d/vocals.wav" "$ep/h3/amb/${shot}_removed_vocals.wav"
  n=$((n + 1))
done
echo "ambience written for $n shots"

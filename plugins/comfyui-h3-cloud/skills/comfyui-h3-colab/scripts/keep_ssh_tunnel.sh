#!/usr/bin/env bash
SESSION_NAME="${1:-minimax-h3}"
LOCAL_PORT="${2:-8188}"
COLAB="${COLAB_BIN:-$(command -v colab)}"      # the colab CLI; set COLAB_BIN if it is not on PATH

while true; do
  /usr/bin/ssh -N -L "0.0.0.0:${LOCAL_PORT}:127.0.0.1:8188" \
    -o StrictHostKeyChecking=no \
    -o UserKnownHostsFile=/dev/null \
    -o ServerAliveInterval=20 \
    -o ServerAliveCountMax=3 \
    -o ExitOnForwardFailure=yes \
    -o ProxyCommand="${COLAB} ssh --proxy-mode -s ${SESSION_NAME}" \
    root@colab
  sleep 10
done

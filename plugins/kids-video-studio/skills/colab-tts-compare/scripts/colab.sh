#!/usr/bin/env bash
# Thin wrapper so PowerShell never has to quote bash: colab.sh <subcommand> [args...]
# WSL paths (/mnt/<drive>/...) are passed straight through. Session defaults to "tts".
C="${COLAB_BIN:-$(command -v colab)}"
S="${COLAB_SESSION:-tts}"
sub="$1"; shift
case "$sub" in
  exec)     # exec <file.py> [timeout] [KEY=VALUE ...]  -> env vars inside the remote kernel
            f="$1"; t="${2:-120}"; shift 2 || shift $#
            envs=(); for kv in "$@"; do envs+=(--env "$kv"); done
            $C exec -s "$S" -f "$f" --timeout "$t" "${envs[@]}" 2>&1 | grep -v '^\[colab\]' ;;
  upload)   $C upload -s "$S" "$1" "$2" 2>&1 | grep -v '^\[colab\]' ;;
  download) $C download -s "$S" "$1" "$2" 2>&1 | grep -v '^\[colab\]' ;;
  status)   $C status 2>&1 | grep -v '^\[colab\]' ;;
  usage)    $C usage 2>&1 | grep -v '^\[colab\]' ;;
  stop)     $C stop -s "$S" 2>&1 | grep -v '^\[colab\]'; $C status 2>&1 | grep -v '^\[colab\]' ;;
  *) echo "unknown subcommand $sub"; exit 2 ;;
esac

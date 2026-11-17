#!/usr/bin/env bash
# Runs ON the Colab VM. One isolated Python 3.11 venv per engine (their pins conflict), installed in parallel.
# Log: /content/tts/setup.log, per-engine: /content/tts/setup_<engine>.log, done marker: /content/tts/setup.done
set -u
cd /content/tts
export UV_LINK_MODE=copy HF_HUB_ENABLE_HF_TRANSFER=0
apt-get -qq update >/dev/null 2>&1 && apt-get -qq install -y espeak-ng >/dev/null 2>&1 && echo "espeak-ng ok"

mk() {  # mk <engine> <pip args...>
  local e="$1"; shift
  {
    uv venv --seed --python 3.11 "/content/venv/$e" &&
    VIRTUAL_ENV="/content/venv/$e" uv pip install --python "/content/venv/$e/bin/python" "$@" &&
    echo "INSTALL_OK $e"
  } > "setup_$e.log" 2>&1 || echo "INSTALL_FAIL $e" >> "setup_$e.log"
}

mk kokoro "kokoro>=0.9.4" soundfile "misaki[en]" &
mk chatterbox chatterbox-tts soundfile "setuptools<81" &   # its watermarker imports pkg_resources
mk orpheus torch torchaudio "transformers>=4.46,<5" accelerate snac soundfile &
mk dia "git+https://github.com/nari-labs/dia.git" soundfile &
wait

for e in kokoro chatterbox orpheus dia; do tail -n 1 "setup_$e.log"; done
# spaCy model for Kokoro's English G2P (misaki would otherwise try to download it at first use)
/content/venv/kokoro/bin/python -m spacy download en_core_web_sm >> setup_kokoro.log 2>&1 && echo "spacy model ok"
touch setup.done

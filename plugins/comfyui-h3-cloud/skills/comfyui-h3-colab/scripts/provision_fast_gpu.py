#!/usr/bin/env python3
"""
Fast-GPU Provisioner & Automated Setup for MiniMax H3 on Google Colab.
STRICT RULE: Only requests high-speed GPUs (A100 80GB --high-mem, H100, A100 40GB).
NEVER falls back to L4 or T4 to avoid slow PCIe swapping.
"""
import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

COLAB = os.environ.get("COLAB_BIN") or shutil.which("colab") or "colab"      # the colab CLI; set COLAB_BIN if it is not on PATH
SCRIPT_DIR = Path(__file__).resolve().parent
SETUP_SH = str(SCRIPT_DIR / "setup_colab_h3.sh")

FAST_GPU_CANDIDATES = [
    ["--gpu", "A100", "--high-mem"],
    ["--gpu", "H100", "--high-mem"],
    ["--gpu", "H100"],
    ["--gpu", "A100"],
]


def main():
    parser = argparse.ArgumentParser(description="Provision a fast Colab GPU (A100/H100 only) and deploy MiniMax H3")
    parser.add_argument("--session", "-s", default="minimax-h3", help="Colab session name")
    parser.add_argument("--mode", choices=["quant", "bf16"], default="quant", help="Model tier (default: quant)")
    parser.add_argument("--with-h3-image", default="1", choices=["0", "1"], help="Also download MiniMax-H3-Image (default: 1)")
    parser.add_argument("--with-qwen-t2i", default="0", choices=["0", "1"], help="Also download Qwen-Image-2512 T2I (default: 0)")
    parser.add_argument("--with-upscale", default="1", choices=["0", "1"], help="Also download RelayVSR x2 & RealESRGAN 1080p video upscalers")
    parser.add_argument("--rounds", type=int, default=4, help="Retry rounds across fast GPU candidates")
    args = parser.parse_args()

    assigned = False
    for round_idx in range(1, args.rounds + 1):
        for flags in FAST_GPU_CANDIDATES:
            cmd = [COLAB, "new", "-s", args.session] + flags
            print(f"[Round {round_idx}/{args.rounds}] Requesting fast GPU: {' '.join(cmd)}", flush=True)
            try:
                res = subprocess.run(cmd, capture_output=True, text=True, timeout=75)
                if res.returncode == 0 and "Session READY" in res.stdout:
                    print(res.stdout, flush=True)
                    assigned = True
                    break
                err_lines = [
                    l for l in (res.stdout + "\n" + res.stderr).splitlines()
                    if "Error" in l or "Unavailable" in l or "TooMany" in l
                ]
                print(f"  -> Unavailable ({err_lines[-1] if err_lines else res.returncode})", flush=True)
                if any("TooManyAssignmentsError" in l for l in err_lines):
                    print("ERROR: Account already has maximum active GPU sessions. Run `colab status`.", flush=True)
                    sys.exit(2)
            except subprocess.TimeoutExpired:
                print("  -> Assign request timed out after 75s, checking `colab status`...", flush=True)
                st = subprocess.run([COLAB, "status"], capture_output=True, text=True)
                if args.session in st.stdout:
                    print(st.stdout, flush=True)
                    assigned = True
                    break
            time.sleep(3)
        if assigned:
            break

    if not assigned:
        print("ERROR: Could not allocate a fast GPU (A100/H100). Refusing to fall back to slow L4/T4.", flush=True)
        sys.exit(1)

    print(f"[Deploy] Uploading {SETUP_SH} to session '{args.session}'...", flush=True)
    subprocess.run([COLAB, "upload", "-s", args.session, SETUP_SH, "/content/setup_colab_h3.sh"], check=True)

    print(f"[Deploy] Running setup_colab_h3.sh (MODE={args.mode} WITH_H3_IMAGE={args.with_h3_image} WITH_QWEN_T2I={args.with_qwen_t2i} WITH_UPSCALE={args.with_upscale}) via SSH...", flush=True)
    ssh_cmd = [
        "/usr/bin/ssh",
        "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null",
        "-o", "ServerAliveInterval=20",
        "-o", f"ProxyCommand={COLAB} ssh --proxy-mode -s {args.session}",
        "root@colab",
        f"sed -i 's/\\r$//' /content/setup_colab_h3.sh && MODE={args.mode} WITH_H3_IMAGE={args.with_h3_image} WITH_QWEN_T2I={args.with_qwen_t2i} WITH_UPSCALE={args.with_upscale} bash /content/setup_colab_h3.sh",
    ]
    sys.exit(subprocess.run(ssh_cmd).returncode)


if __name__ == "__main__":
    main()

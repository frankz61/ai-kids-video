"""Keep trying to power on a shut-down AutoDL Pro instance until a GPU is free (popular cards such as the 5090 are often
all taken; a free one is grabbed within seconds by whoever asks first).

  python3 power_on_retry.py --uuid pro-xxxx --start-command "..." [--every 15] [--hours 6]
Tries every --every seconds (doubled while the API says it is busy), stops as soon as the instance is running and exits 0;
gives up after --hours and exits 1. Each attempt that succeeds starts GPU billing, so only run it when the user wants the
machine. Token: same lookup as autodl_pro_client.py (--token, $AUTODL_TOKEN, ~/.config/autodl/token).
"""
import argparse, sys, time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import autodl_pro_client as c  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--uuid", required=True)
    ap.add_argument("--start-command", default="")
    ap.add_argument("--every", type=float, default=15)
    ap.add_argument("--hours", type=float, default=6)
    ap.add_argument("--token")
    a = ap.parse_args()
    tok = c.load_token(a.token)
    t0, n, msg = time.time(), 0, ""
    while time.time() - t0 < a.hours * 3600:
        try:
            st = c.get_status(tok, a.uuid)
        except Exception as e:  # network hiccup: try again
            st = f"err {str(e)[:120]}"
        if st == "running":
            print(time.strftime("%H:%M:%S"), "RUNNING after", n, "tries", flush=True)
            return 0
        idle = st in ("shutdown", "") or st.startswith("err")
        if idle:
            n += 1
            try:
                body = {"instance_uuid": a.uuid, "payload": "gpu"}
                if a.start_command:
                    body["start_command"] = a.start_command
                r = c.api_call(tok, "/api/v1/dev/instance/pro/power_on", "POST", body)
                msg = f"{r.get('code')} {str(r.get('msg'))[:100]}"
            except Exception as e:
                msg = str(e)[:160]
            print(time.strftime("%H:%M:%S"), f"try {n} status={st}:", msg, flush=True)
        else:                       # starting / shutting down: just wait for it
            print(time.strftime("%H:%M:%S"), "status", st, flush=True)
        busy = "busy" in msg.lower() or "忙" in msg
        time.sleep((a.every * 2 if busy else a.every) if idle else 10)
    print(f"gave up after {a.hours} h", flush=True)
    return 1


if __name__ == "__main__":
    sys.exit(main())

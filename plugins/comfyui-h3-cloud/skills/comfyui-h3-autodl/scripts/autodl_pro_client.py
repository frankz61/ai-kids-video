#!/usr/bin/env python3
"""
AutoDL Container Instance Pro API Client (`https://api.autodl.com`).
Supports balance check, regional GPU stock query, instance listing/creation/snapshot,
power_on/power_off/release, and private image saving.
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

API_HOST = "https://api.autodl.com"
DEFAULT_TOKEN_PATH = Path.home() / ".config" / "autodl" / "token"

DEFAULT_REGIONS = ["beijingDC2", "westDC3", "westDC2", "chongqingDC1", "neimengDC3"]
# Ordered roughly from lowest cost (>=32GB VRAM) upward
DEFAULT_SPECS = ["v-32g-p", "v-48g-350w", "v-48g", "5090d-p", "5090-p", "pro6000-p", "4090D"]


def load_token(cli_token: str | None = None) -> str:
    if cli_token:
        return cli_token.strip()
    env_tok = os.environ.get("AUTODL_TOKEN", "").strip()
    if env_tok:
        return env_tok
    if DEFAULT_TOKEN_PATH.is_file():
        return DEFAULT_TOKEN_PATH.read_text(encoding="utf-8").strip()
    raise RuntimeError(
        f"AutoDL developer token not found. Pass --token, set AUTODL_TOKEN, or save to {DEFAULT_TOKEN_PATH}"
    )


def api_call(token: str, path: str, method: str = "POST", body: dict | None = None, timeout: int = 20) -> dict:
    url = f"{API_HOST}{path}"
    data = json.dumps(body if body is not None else {}).encode("utf-8") if body is not None or method == "POST" else None
    headers = {
        "Authorization": token,
        "Content-Type": "application/json",
    }
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {e.code} on {method} {path}: {raw}") from None


def cmd_balance(token: str, args):
    res = api_call(token, "/api/v1/dev/wallet/balance", "POST", {})
    data = res.get("data") or {}
    assets = data.get("assets", 0)
    blocked = data.get("blocked_asset", 0)
    print(f"UID     : {data.get('uid')}")
    print(f"Balance : ¥{assets / 1000.0:.2f} (assets={assets}, blocked={blocked}, voucher={data.get('voucher_balance', 0)})")


def cmd_stock(token: str, args):
    regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    for r in regions:
        res = api_call(token, "/api/v1/dev/machine/region/gpu_stock", "POST", {"region_sign": r})
        items = res.get("data") or []
        avail = {}
        for item in items:
            for gpu, info in item.items():
                idle = info.get("idle_gpu_num", 0)
                if idle > 0 or args.all:
                    avail[gpu] = f"{idle}/{info.get('total_gpu_num', 0)}"
        print(f"{r:14s}: {avail}")


def get_snapshot(token: str, instance_uuid: str) -> dict:
    res = api_call(token, f"/api/v1/dev/instance/pro/snapshot?instance_uuid={instance_uuid}", "GET")
    return res.get("data") or {}


def get_status(token: str, instance_uuid: str) -> str:
    res = api_call(token, f"/api/v1/dev/instance/pro/status?instance_uuid={instance_uuid}", "GET")
    return str(res.get("data") or "")


def cmd_list(token: str, args):
    res = api_call(token, "/api/v1/dev/instance/pro/list", "POST", {"page_index": 1, "page_size": 50})
    items = (res.get("data") or {}).get("list") or []
    if not items:
        print("No Pro instances found.")
        return
    for it in items:
        uid = it.get("uuid")
        status = it.get("status")
        spec = it.get("gpu_spec_uuid")
        region = it.get("region_sign")
        snap = {}
        try:
            snap = get_snapshot(token, uid)
        except Exception:
            pass
        price = snap.get("payg_price")
        price_str = f"¥{price / 1000.0:.2f}/hr" if isinstance(price, (int, float)) else "N/A"
        gpu_alias = snap.get("snapshot_gpu_alias_name", "")
        ssh_cmd = snap.get("ssh_command", "")
        pwd = snap.get("root_password", "")
        print(
            f"{uid} | name={it.get('name')} | {region} | spec={spec} ({gpu_alias}) | "
            f"{price_str} | status={status} | ssh={ssh_cmd} | pwd={pwd}"
        )


def cmd_create(token: str, args):
    regions = [r.strip() for r in args.regions.split(",") if r.strip()]
    specs = [s.strip() for s in args.specs.split(",") if s.strip()]

    instance_uuid = None
    chosen = None
    # Try spec-first or region-first depending on --region-first (default region-first to prefer beijingDC2 /root/autodl-fs)
    pairs = [(r, s) for r in regions for s in specs] if args.region_first else [(r, s) for s in specs for r in regions]
    for region, spec in pairs:
        payload = {
            "req_gpu_amount": 1,
            "expand_system_disk_by_gb": args.expand_disk,
            "gpu_spec_uuid": spec,
            "image_uuid": args.image_uuid,
            "cuda_v_from": args.cuda_from,
            "instance_name": args.name,
        }
        if region != "auto":
            payload["data_center_list"] = [region]
        if args.start_command:
            payload["start_command"] = args.start_command
        print(f"Trying create: region={region}, gpu_spec_uuid={spec}, cuda_v_from={args.cuda_from}...", flush=True)
        res = api_call(token, "/api/v1/dev/instance/pro/create", "POST", payload)
        if res.get("code") == "Success" and res.get("data"):
            instance_uuid = res["data"]
            chosen = (region, spec)
            print(f"Created instance_uuid={instance_uuid} ({region}, {spec})", flush=True)
            break
        print(f"  -> Rejected: code={res.get('code')} msg={res.get('msg')}", flush=True)

    if not instance_uuid:
        raise RuntimeError("Failed to create instance across all (region, spec) candidates.")

    print("Waiting for instance to reach running state with SSH ready...", flush=True)
    snap = {}
    for _ in range(90):
        st = get_status(token, instance_uuid)
        if st == "running":
            snap = get_snapshot(token, instance_uuid)
            if snap.get("ssh_port") and snap.get("proxy_host"):
                break
        elif st in ("shutdown", "starting_failed", "create_failed"):
            snap = get_snapshot(token, instance_uuid)
            raise RuntimeError(f"Instance entered terminal state '{st}': {snap}")
        time.sleep(2)

    snap = snap or get_snapshot(token, instance_uuid)
    price = snap.get("payg_price")
    orig_price = snap.get("origin_pay_price")
    print("\n=== PRO INSTANCE READY ===")
    print(f"Instance UUID : {instance_uuid}")
    print(f"Region / Spec : {chosen[0]} ({snap.get('region_sign')}) / {chosen[1]}")
    print(f"GPU Model     : {snap.get('snapshot_gpu_alias_name')}")
    if isinstance(price, (int, float)):
        print(f"Hourly Price  : ¥{price / 1000.0:.2f}/hr (original: ¥{(orig_price or 0) / 1000.0:.2f}/hr)")
    print(f"SSH Command   : {snap.get('ssh_command')}")
    print(f"SSH Host/Port : {snap.get('proxy_host')}:{snap.get('ssh_port')}")
    print(f"Root Password : {snap.get('root_password')}")


def cmd_power_off(token: str, args):
    res = api_call(token, "/api/v1/dev/instance/pro/power_off", "POST", {"instance_uuid": args.uuid})
    print(json.dumps(res, ensure_ascii=False))


def cmd_power_on(token: str, args):
    body = {"instance_uuid": args.uuid, "payload": "gpu"}
    if args.start_command:
        body["start_command"] = args.start_command
    res = api_call(token, "/api/v1/dev/instance/pro/power_on", "POST", body)
    print(json.dumps(res, ensure_ascii=False))


def cmd_release(token: str, args):
    st = get_status(token, args.uuid)
    if st != "shutdown":
        print(f"Instance is '{st}', powering off first...", flush=True)
        api_call(token, "/api/v1/dev/instance/pro/power_off", "POST", {"instance_uuid": args.uuid})
        for _ in range(30):
            if get_status(token, args.uuid) == "shutdown":
                break
            time.sleep(2)
    res = api_call(token, "/api/v1/dev/instance/pro/release", "POST", {"instance_uuid": args.uuid})
    print(json.dumps(res, ensure_ascii=False))


def cmd_save_image(token: str, args):
    res = api_call(
        token,
        "/api/v1/dev/instance/pro/image/save",
        "POST",
        {"instance_uuid": args.uuid, "image_name": args.image_name},
    )
    print(json.dumps(res, ensure_ascii=False))


def main():
    parser = argparse.ArgumentParser(description="AutoDL Container Instance Pro API Client")
    parser.add_argument("--token", default=None, help="AutoDL Developer Token (or set AUTODL_TOKEN / ~/.config/autodl/token)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("balance", help="Query wallet balance")

    p_stock = sub.add_parser("stock", help="Query regional GPU availability")
    p_stock.add_argument("--regions", default="beijingDC2,westDC3,westDC2,neimengDC3,chongqingDC1")
    p_stock.add_argument("--all", action="store_true", help="Include GPUs with 0 idle count")

    sub.add_parser("list", help="List all Pro instances and SSH/pricing snapshots")

    p_create = sub.add_parser("create", help="Create cheapest >=32GB GPU Pro instance")
    p_create.add_argument("--regions", default="beijingDC2,auto")
    p_create.add_argument("--specs", default="v-32g-p,v-48g-350w,v-48g,5090d-p,5090-p,pro6000-p,4090D")
    p_create.add_argument("--image-uuid", default="base-image-l2t43iu6uk")
    p_create.add_argument("--cuda-from", type=int, default=113)
    p_create.add_argument("--expand-disk", type=int, default=0)
    p_create.add_argument("--name", default="minimax-h3-pro")
    p_create.add_argument("--start-command", default="")
    p_create.add_argument("--region-first", action="store_true", default=False)
    p_create.add_argument("--spec-first", dest="region_first", action="store_false")

    p_off = sub.add_parser("power-off", help="Power off a Pro instance")
    p_off.add_argument("--uuid", required=True)

    p_on = sub.add_parser("power-on", help="Power on a Pro instance")
    p_on.add_argument("--uuid", required=True)
    p_on.add_argument("--start-command", default="")

    p_rel = sub.add_parser("release", help="Power off and release a Pro instance")
    p_rel.add_argument("--uuid", required=True)

    p_save = sub.add_parser("save-image", help="Save a Pro instance as a private image")
    p_save.add_argument("--uuid", required=True)
    p_save.add_argument("--image-name", required=True)

    args = parser.parse_args()
    token = load_token(args.token)
    if args.cmd == "balance":
        cmd_balance(token, args)
    elif args.cmd == "stock":
        cmd_stock(token, args)
    elif args.cmd == "list":
        cmd_list(token, args)
    elif args.cmd == "create":
        cmd_create(token, args)
    elif args.cmd == "power-off":
        cmd_power_off(token, args)
    elif args.cmd == "power-on":
        cmd_power_on(token, args)
    elif args.cmd == "release":
        cmd_release(token, args)
    elif args.cmd == "save-image":
        cmd_save_image(token, args)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Profile per-node execution time using ComfyUI's websocket events.

Runs one warm-up (plain HTTP) then one profiled run per workflow. Node time is
measured from the "executing" event to that node's "executed" event, so text
encoder load/encode and sampler time can be reported separately.
"""

import argparse
import json
import subprocess
import threading
import time
import urllib.request
import uuid
from pathlib import Path

from websockets.sync.client import connect

from bench_workflows import PROMPT, WORKFLOWS, prepare_workflow

COMFY_URL = "http://127.0.0.1:8188"
WS_URL = "ws://127.0.0.1:8188/ws?clientId="


def http_json(url, payload=None, method=None, timeout=30):
    data = None
    headers = {}
    if payload is not None:
        data = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def gpu_memory_used_mb():
    try:
        out = subprocess.check_output(
            ["nvidia-smi", "--query-gpu=memory.used", "--format=csv,noheader,nounits", "-i", "0"],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return int(float(out.strip().splitlines()[0]))
    except Exception:
        return None


def submit(workflow, client_id):
    return http_json(
        f"{COMFY_URL}/prompt",
        {"prompt": workflow, "client_id": client_id},
        method="POST",
        timeout=30,
    )["prompt_id"]


def wait_history(prompt_id, timeout=1800):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            hist = http_json(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
        except Exception:
            hist = {}
        if prompt_id in hist:
            return hist[prompt_id]
        time.sleep(1)
    raise TimeoutError(prompt_id)


def profile(workflow, classes, timeout=1800):
    client_id = "profiler-" + uuid.uuid4().hex
    events = []
    peak = [gpu_memory_used_mb()]
    stop = threading.Event()

    def monitor():
        while not stop.is_set():
            v = gpu_memory_used_mb()
            if v is not None:
                peak[0] = max(peak[0], v)
            stop.wait(0.2)

    mon = threading.Thread(target=monitor, daemon=True)
    mon.start()

    with connect(WS_URL + client_id, max_size=None, open_timeout=10) as ws:
        prompt_id = submit(workflow, client_id)
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = ws.recv(timeout=timeout)
            if not isinstance(raw, str):
                continue
            msg = json.loads(raw)
            if msg.get("data", {}).get("prompt_id") not in (None, prompt_id):
                continue
            t = time.time()
            typ = msg.get("type")
            if typ in ("executing", "executed", "execution_success", "execution_error", "execution_cached"):
                events.append((t, typ, msg.get("data", {})))
            if typ in ("execution_success", "execution_error"):
                break

    stop.set()
    mon.join(timeout=3)

    starts = [(e[0], e[2].get("node")) for e in events if e[1] == "executing"]
    terminal = None
    for t, typ, data in events:
        if typ in ("execution_success", "execution_error"):
            terminal = t
    cached = []
    for t, typ, data in events:
        if typ == "execution_cached":
            cached = data.get("nodes") or []

    rows = []
    for i, (t, node) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else (terminal or t)
        info = classes.get(node, {})
        rows.append(
            {
                "node": node,
                "class": info.get("class_type"),
                "title": (info.get("_meta") or {}).get("title"),
                "seconds": round(end - t, 3),
            }
        )
    rows.sort(key=lambda r: r["seconds"], reverse=True)
    return {
        "prompt_id": prompt_id,
        "peak_vram_mb": peak[0],
        "total_events_seconds": round(terminal - starts[0][0], 3) if starts and terminal else None,
        "cached_nodes": cached,
        "nodes": rows,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*", choices=sorted(WORKFLOWS))
    ap.add_argument("--base-seed", type=int, default=4200)
    ap.add_argument("--out", default="node_profile_results.json")
    args = ap.parse_args()

    names = args.only or ["zimage", "krea2", "boogu"]
    results = {}
    for name in names:
        wf = json.loads(WORKFLOWS[name].read_text())
        prepared, meta = prepare_workflow(wf, name, 0, args.base_seed)
        print(f"\n[{name}] warm-up ...", flush=True)
        warm_pid = submit(prepared, "warmup-" + name)
        wait_history(warm_pid)
        # Unique prompt defeats ComfyUI's node cache so the text encoder runs
        # again while models stay warm.
        if meta.get("prompt_node"):
            prepared[meta["prompt_node"]]["inputs"]["text"] = PROMPT + f" [{name} profile]"
        print(f"[{name}] profiled run ...", flush=True)
        res = profile(prepared, wf)
        results[name] = res
        print(f"  peak VRAM {res['peak_vram_mb']} MB", flush=True)
        for row in res["nodes"][:10]:
            print(f"  {row['seconds']:7.2f}s  {row['node']:<7} {row['class']}", flush=True)

    Path(args.out).write_text(json.dumps(results, indent=2))
    print(f"\nWrote {args.out}")


if __name__ == "__main__":
    main()

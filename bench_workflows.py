#!/usr/bin/env python3
"""Benchmark for the llmMobile ComfyUI workflows.

Submits the existing API-format workflows to ComfyUI, varies the seed per run
to defeat ComfyUI's node cache, and records wall time, sampler time, and peak
P100 VRAM. Also pokes the llm-mobile lifecycle endpoint so its 10-minute idle
watchdog does not stop ComfyUI during the benchmark.
"""

import argparse
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path

COMFY_URL = "http://127.0.0.1:8188"
LLM_URL = "http://127.0.0.1:8000"

LLM_MOBILE = Path("/home/nui/dev/llmMobile")
WORKFLOWS = {
    "zimage": LLM_MOBILE / "MyZimage_turbo.json",
    "krea2": LLM_MOBILE / "MyKrea2E_Turbo.json",
    "boogu": LLM_MOBILE / "My_Boogu_Image_Turbo_T2I.json",
    "krea2_edit": LLM_MOBILE / "Image1_krea2_edit.json",
    "krea2_edit_dual": LLM_MOBILE / "Img2-to-Img1-text-krea2_edit.json",
}
PROMPT = (
    "A red fox sitting in a snowy pine forest at golden hour, photorealistic, "
    "detailed fur, cinematic lighting, sharp focus."
)


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
            [
                "nvidia-smi",
                "--query-gpu=memory.used",
                "--format=csv,noheader,nounits",
                "-i",
                "0",
            ],
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return int(float(out.strip().splitlines()[0]))
    except Exception:
        return None


def wait_for_comfy(timeout=180):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            http_json(f"{COMFY_URL}/system_stats", timeout=3)
            return True
        except Exception:
            time.sleep(2)
    return False


def touch_activity():
    try:
        http_json(f"{LLM_URL}/api/comfyui/start", {}, method="POST", timeout=5)
    except Exception:
        pass


def find_node(workflow, class_types):
    for node_id, node in workflow.items():
        if isinstance(node, dict) and node.get("class_type") in class_types:
            return node_id, node
    return None, None


def prepare_workflow(workflow, workflow_name, run_index, seed):
    wf = json.loads(json.dumps(workflow))

    prompt_id, prompt_node = find_node(wf, {"CLIPTextEncode"})
    if prompt_node is not None:
        prompt_node["inputs"]["text"] = PROMPT

    latent_id, latent_node = find_node(
        wf, {"EmptyLatentImage", "EmptySD3LatentImage"}
    )
    sampler_id, sampler_node = find_node(
        wf, {"KSampler", "KSamplerAdvanced"}
    )
    save_id, save_node = find_node(wf, {"SaveImage"})

    if sampler_node is not None:
        sampler_node["inputs"]["seed"] = seed

    if save_node is not None:
        save_node["inputs"]["filename_prefix"] = (
            f"bench-{workflow_name}-{run_index}-{seed}"
        )

    return wf, {
        "prompt_node": prompt_id,
        "latent_node": latent_id,
        "sampler_node": sampler_id,
        "save_node": save_id,
        "width": latent_node["inputs"].get("width") if latent_node else None,
        "height": latent_node["inputs"].get("height") if latent_node else None,
        "steps": sampler_node["inputs"].get("steps") if sampler_node else None,
        "sampler": sampler_node["inputs"].get("sampler_name") if sampler_node else None,
        "scheduler": sampler_node["inputs"].get("scheduler") if sampler_node else None,
        "cfg": sampler_node["inputs"].get("cfg") if sampler_node else None,
        "seed": seed,
    }


def wait_for_history(prompt_id, timeout=1200):
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            history = http_json(f"{COMFY_URL}/history/{prompt_id}", timeout=10)
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                history = {}
            else:
                raise
        if prompt_id in history:
            return history[prompt_id]
        time.sleep(1)
    raise TimeoutError(f"prompt {prompt_id} did not finish within {timeout}s")


def timestamps_from_messages(history):
    messages = (history.get("status") or {}).get("messages") or []
    start = end = None
    for item in messages:
        if not isinstance(item, list) or len(item) < 2:
            continue
        event = item[0]
        data = item[1] if isinstance(item[1], dict) else {}
        ts = data.get("timestamp")
        if ts is None and len(item) >= 3:
            ts = item[2]
        if ts is None:
            continue
        if event == "execution_start" and start is None:
            start = ts
        elif event in ("execution_success", "execution_error"):
            end = ts
    if start is not None and end is not None:
        delta = float(end) - float(start)
        # ComfyUI timestamps are epoch milliseconds.
        return delta / 1000.0 if delta > 1000 else delta
    return None


def run_one(workflow_name, workflow_path, run_index, seed, timeout):
    workflow = json.loads(workflow_path.read_text())
    wf, meta = prepare_workflow(workflow, workflow_name, run_index, seed)

    touch_activity()
    peak_mb = [gpu_memory_used_mb()]
    stop_monitor = threading.Event()

    def monitor():
        while not stop_monitor.is_set():
            used = gpu_memory_used_mb()
            if used is not None:
                peak_mb[0] = max(peak_mb[0], used)
            stop_monitor.wait(0.5)

    monitor_thread = threading.Thread(target=monitor, daemon=True)
    monitor_thread.start()

    started = time.time()
    try:
        response = http_json(
            f"{COMFY_URL}/prompt",
            {"prompt": wf, "client_id": "bench-phase0"},
            method="POST",
            timeout=30,
        )
        prompt_id = response["prompt_id"]
        history = wait_for_history(prompt_id, timeout=timeout)
    finally:
        stop_monitor.set()
        monitor_thread.join(timeout=5)

    wall = time.time() - started
    status = history.get("status") or {}
    status_str = status.get("status_str", "unknown")
    exec_time = timestamps_from_messages(history)

    return {
        "workflow": workflow_name,
        "run": run_index,
        "seed": seed,
        "prompt_id": prompt_id,
        "wall_seconds": round(wall, 3),
        "execution_seconds": round(exec_time, 3) if exec_time is not None else None,
        "peak_vram_mb": peak_mb[0],
        "status": status_str,
        "meta": meta,
        "messages": status.get("messages"),
    }


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runs", type=int, default=3, help="measured runs per workflow")
    parser.add_argument("--warmup", type=int, default=1, help="warmup runs per workflow")
    parser.add_argument("--base-seed", type=int, default=4200)
    parser.add_argument("--timeout", type=int, default=1200, help="per-prompt timeout")
    parser.add_argument(
        "--only",
        nargs="*",
        choices=sorted(WORKFLOWS),
        help="limit to specific workflows",
    )
    parser.add_argument(
        "--out",
        default="/home/nui/dev/comfyui-container/baseline_results.json",
    )
    args = parser.parse_args()

    names = args.only or ["zimage", "krea2", "boogu"]
    if not wait_for_comfy():
        raise SystemExit("ComfyUI did not become ready")

    keepalive_stop = threading.Event()

    def keepalive():
        while not keepalive_stop.is_set():
            touch_activity()
            keepalive_stop.wait(120)

    keepalive_thread = threading.Thread(target=keepalive, daemon=True)
    keepalive_thread.start()

    results = []
    try:
        for name in names:
            path = WORKFLOWS[name]
            total = args.warmup + args.runs
            for run_index in range(total):
                is_warmup = run_index < args.warmup
                measured_index = run_index - args.warmup
                seed = args.base_seed + run_index
                label = "warmup" if is_warmup else f"run {measured_index + 1}"
                print(f"\n[{name}] {label} seed={seed}", flush=True)
                result = run_one(
                    name, path, run_index, seed, timeout=args.timeout
                )
                result["warmup"] = is_warmup
                results.append(result)
                print(
                    "  wall={wall_seconds}s exec={execution_seconds}s "
                    "peak_vram={peak_vram_mb}MB status={status}".format(**result),
                    flush=True,
                )
                if result["status"] != "success":
                    print(json.dumps(result.get("messages"), indent=2)[:4000])
    finally:
        keepalive_stop.set()
        keepalive_thread.join(timeout=5)

    Path(args.out).write_text(json.dumps(results, indent=2))
    print(f"\nWrote {args.out}")

    print("\nMeasured runs (mean):")
    for name in names:
        runs = [
            r
            for r in results
            if r["workflow"] == name and not r.get("warmup") and r["status"] == "success"
        ]
        if not runs:
            print(f"  {name}: no successful measured runs")
            continue
        mean_wall = sum(r["wall_seconds"] for r in runs) / len(runs)
        execs = [r["execution_seconds"] for r in runs if r["execution_seconds"]]
        mean_exec = sum(execs) / len(execs) if execs else None
        peak = max(r["peak_vram_mb"] for r in runs if r["peak_vram_mb"])
        print(
            f"  {name}: wall {mean_wall:.2f}s"
            + (f", exec {mean_exec:.2f}s" if mean_exec else "")
            + f", peak VRAM {peak} MB, n={len(runs)}"
        )


if __name__ == "__main__":
    main()

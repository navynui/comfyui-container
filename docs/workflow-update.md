# Workflow Update — 2026-11-04

Summary of the changes made after the Phase 3 benchmarks. The goal was lower
disk usage and lower latency for real llmMobile usage without touching sampler
settings, resolution, or model quality beyond what was measured.

## 1. Krea2 default switched to `Q5_K_M`

All Krea2 API workflows now load `krea2_turbo-Q5_K_M.gguf` instead of
`krea2_turbo-Q6_K.gguf`:

- `~/dev/llmMobile/MyKrea2E_Turbo.json` (integrated `krea2-turbo`)
- `~/dev/llmMobile/MyKrea2_Turbo.json`
- `~/dev/llmMobile/Image1_krea2_edit.json` (integrated `krea2-edit`, single image)
- `~/dev/llmMobile/Img2-to-Img1-text-krea2_edit.json` (integrated `krea2-edit`, dual image)
- `ComfyUI/user/default/workflows/MyKrea2_Turbo.json`
- `ComfyUI/user/default/workflows/krea2_identity_edit.json`

**Reasoning:** same speed as Q6_K (118.15 vs 118.62 s T2I; 395.8 vs 396.5 s
identity edit), but 1.4–1.5 GB less peak VRAM. The identity-edit LoRA was
validated separately: faces/identities preserved, mean pixel diff 3.7–4.1/255,
no black/NaN. Q6_K was removed, so it is no longer available as a fallback.

## 2. Warm cooldown: back-to-back prompts no longer reload models

Changed `_post_queue_cleanup` in `services/comfy/worker.py`. Previously ComfyUI
was unloaded immediately after every generation, then the LLM was restored
180 s later. That meant any follow-up prompt paid a cold model load even if it
arrived seconds later.

Now ComfyUI stays warm during the 180 s cooldown, and VRAM is freed only just
before the LLM is restored. If a new generation request arrives, the cooldown
task is cancelled and the loaded models are reused.

**Reasoning:** Phase 3 cold-vs-warm data shows the reload cost is significant,
especially Boogu (cold KSampler ~126 s vs 35.6 s warm; fp8 weight load is
deferred into the sampler) and Z-Image (UNET loader 10.6 s + CLIP loader 3.9 s).
Krea2 is smaller (~3.8 s CLIP loader), but the saving is still real.

**Scope:** the first generation after the container has been idle (10-minute
watchdog) is still cold. The gain applies to repeat generations within the
180 s cooldown.

## 3. Fixed seed propagation in multi-workflow runs

Changed `_make_sub_items` in `services/comfy/api.py` to pass `req.seed` into
each sub-item instead of `None`.

**Reasoning:** when selecting several workflows at once, the UI seed was
ignored and each workflow generated a different random seed. Passing it through
makes multi-workflow runs reproducible and matches the benchmark A/B method
(same seed per comparison).

## 4. Disk cleanup (~37 GiB freed)

Deleted the rejected/obsolete weight files:

| File | Size |
|---|---:|
| `models/unet/z_image_turbo-Q8_0.gguf` | 7.22 GB |
| `models/unet/z_image_turbo-Q6_K.gguf` | 5.91 GB |
| `models/unet/Boogu-Turbo-V2_dit-Q5_0.gguf` | 7.99 GB |
| `models/unet/boogu-turbo-dit-Q5_0.gguf` | 8.04 GB |
| `models/unet/krea2_turbo-Q6_K.gguf` | 10.58 GB |

Also deleted the test-only workflows that referenced them:
`MyZimage_turbo_GGUF_{Q8,Q6K}.json`,
`My_Boogu_Image_Turbo_GGUF{,_V1}.json`, and the redundant
`MyKrea2E_Turbo_Q5KM.json` / `Image1_krea2_edit_Q5KM.json`.

`krea2_turbo-Q5_K_M.gguf` is now the only UNET GGUF left. Free space went from
~55 GB to ~91 GB.

## 5. Benchmark harness cleanup

`bench_workflows.py` now lists only the five integrated workflows:
`zimage`, `krea2`, `boogu`, `krea2_edit`, `krea2_edit_dual`. Entries whose
model files were deleted are gone.

## Deliberately unchanged

- **Boogu stays on `fp8_scaled`.** Q5_0 GGUF was 11% slower (41.18 vs 37.05 s)
  for a 2.2 GB VRAM saving; not worth it as the default on 16 GB.
- **Z-Image stays on bf16.** Q8_0 was neutral and Q6_K was 2% slower with only
  680 MB saved; the P100 runs FP32 compute, so GGUF does not help.
- **Text encoders unchanged.** Profiling showed no end-to-end win from moving
  them; Boogu's 8B encoder cannot stay resident with its DiT in 16 GB.
- **xformers stays removed.** No speed gain, and the SDPA stack is the pinned,
  known-good configuration.
- **No sampler, step, or resolution changes.** Those would change quality and
  were not benchmarked.
- **`krea2_sunsetblur.safetensors` kept.** It is used by the standalone UI
  workflow `My_krea2_turbo_t2i.json`, not by the integrated API workflows.

## Note for testing

The edit benchmark was run with the workflow JSON's 10 KSampler steps, while
llmMobile defaults to **8 edit steps** (`GenerateEditRequest.steps = 8`). The
Q5_K_M validation still applies, but production edit runs are ~20% shorter than
the 396 s benchmark figure. Change the step count in the UI if you want to
compare against the benchmark directly.

## How to verify on the llmMobile interface

1. Start ComfyUI from the Generator tab and confirm it reaches `on`.
2. Run one Krea2 T2I, one Z-Image, and one Boogu generation; check output
   quality and sidecar model names.
3. Run a Krea2 single-image edit and a dual-image edit; confirm identity
   preservation and that the queue completes.
4. Select two workflows, set a fixed seed, and run; both should report the same
   seed in their sidecars.
5. Immediately repeat a Boogu generation. The second run should skip the cold
   model load (noticeably faster than the first).
6. Confirm disk space with `df -h /home`.

## Deployment

The `llm-mobile` image bakes the Python code and workflow JSONs at build time,
so it was rebuilt and recreated (`docker compose build llm-mobile`, then
`up -d --no-deps llm-mobile`). The rebuild initially pulled pydantic 2.14,
which broke the optional MCP server; `requirements.txt` now pins
`pydantic==2.10.6` so the image is reproducible and the MCP server imports
cleanly. FastAPI (port 8000) and MCP (port 8002) are both up.

## Files changed

- `llmMobile/services/comfy/worker.py` — warm cooldown ordering
- `llmMobile/services/comfy/api.py` — seed propagation
- `llmMobile/requirements.txt` — pin `pydantic==2.10.6`
- `llmMobile/MyKrea2E_Turbo.json`, `MyKrea2_Turbo.json`,
  `Image1_krea2_edit.json`, `Img2-to-Img1-text-krea2_edit.json` — Q5_K_M
- `ComfyUI/user/default/workflows/MyKrea2_Turbo.json`,
  `krea2_identity_edit.json` — Q5_K_M
- `comfyui-container/bench_workflows.py` — workflow list cleanup
- `comfyui-container/TODO.md`, `BENCHMARKS.md` — results and removal record
- `comfyui-container/docs/workflow-update.md` — this document

# ComfyUI Benchmarks — Tesla P100

Raw data: `baseline_results.json`, `phase1_fp16vae_results.json`,
`phase2_xformers_results.json`, `phase3_*_results.json`, and
`phase3_node_profiles*.json`; console logs alongside them.
Harness: `bench_workflows.py` (submits the llmMobile API workflows, 1 warm-up + 3 measured runs, varied seeds to bypass cache, touches the llmMobile keepalive) and `profile_nodes.py` (websocket per-node timing).

## Baseline — 2026-11-02

Host: Tesla P100-PCIE-16GB (`sm_60`), driver 580.196.07, 32 GB system RAM.
Stack: ComfyUI `68806143`, torch `2.4.1+cu121`, comfy-kitchen `0.2.16`, no xformers,
native PyTorch SDPA, `NORMAL_VRAM`.

| Workflow | Resolution / steps | Warm-up total | Measured mean total | Measured exec | Peak VRAM | Stability |
|---|---|---:|---:|---:|---:|---|
| z-image-turbo | 1920x1088 / 8 | 184.46 s | **153.20 s** | 152.56 s | 14,497 MB | ±0.01% |
| krea2-turbo | 1280x720 / 8 | 141.24 s | **120.16 s** | 119.44 s | 12,929 MB | ±0.03% |
| boogu-turbo | 720x1280 / 4 | 150.50 s | **38.60 s** | 38.15 s | 11,971 MB | ±0.9% |

Measured runs per workflow: 3. All succeeded; no OOM, no black images, no retries.
Warm-up is slower because it includes cold model loading (Boogu's 8B text encoder
is the largest cold-start cost).

### Key finding: the configured launch flags were never active

`docker-compose.yml` sets `ARGS=--fp16-vae --lowvram`, but this ai-dock image
reads **`COMFYUI_ARGS`**, not `ARGS`. `/etc/comfyui_args.conf` is empty, the
ComfyUI process is `python main.py --disable-auto-launch --port 18188`, and the
log says `Set vram state to: NORMAL_VRAM`. Therefore this baseline is actually:

- default `NORMAL_VRAM`
- no `--fp16-vae`
- SDPA, no xformers

Consequences:

1. The baseline already proves all three workflows, including Boogu, fit and run
   on `NORMAL_VRAM` without `--lowvram` (Boogu peak 11.97 GB). The old premise
   that Boogu needs global `--lowvram` is not supported by this run.
2. Phase 1 is not "remove `--lowvram`"; it is "make the intended args actually
   apply, then benchmark". `--lowvram` should not be re-added without evidence.
3. The old ~90 s Z-Image log was **1280x720**, not the current 1920x1088.
   Adjusting for pixel count, the current SDPA time is consistent; attention
   backend was later tested directly (Phase 2) and gave no gain.

### Observations

- Z-Image is the slowest workflow and sits closest to the 16 GB limit
  (14.5 GB peak). Its 1920x1088 / 8-step sampling dominates the 153 s.
- Krea2 Q6_K is ~120 s for only 8 steps, consistent with GGUF dequantization
  overhead on Pascal; sampler time, not model load, is the cost.
- Boogu is fast once warm (38.6 s); its 150 s warm-up is text-encoder/model load.
- The llmMobile idle watchdog did not stop ComfyUI during the run; the harness
  keepalive worked.

### Reference (pre-freeze, not directly comparable)

From `ComfyUI/comfyui_detail.log`, old stack with `NORMAL_VRAM` + xformers +
torch 2.5.1:

- Z-Image: ~90 s total at **1280x720** (DiT load ~13 s, sampling ~46 s).
- Boogu: ~48–53 s total; sampler ~27 s.
- Krea2: no clean timing captured.

## Phase 1 — `COMFYUI_ARGS=--fp16-vae` (2026-11-02)

Compose key corrected from `ARGS` to `COMFYUI_ARGS`; container recreated. The
flag is now present in the process (`--fp16-vae`), `/etc/comfyui_args.conf`, and
the log still reports `NORMAL_VRAM`. `--lowvram` remains off.

| Workflow | Baseline | Phase 1 | Delta | Peak VRAM (base -> P1) |
|---|---:|---:|---:|---:|
| z-image-turbo | 153.20 s | **151.20 s** | -2.00 s (-1.3%) | 14,497 -> 14,505 MB |
| krea2-turbo | 120.16 s | **118.36 s** | -1.80 s (-1.5%) | 12,929 -> 12,705 MB |
| boogu-turbo | 38.60 s | **37.06 s** | -1.54 s (-4.0%) | 11,971 -> 13,921 MB |

3 measured runs each, all successful, no OOM. The gain is small but consistent.
Boogu peak VRAM rose by ~1.95 GB while getting faster; this is likely the fp16
VAE path keeping more workspace resident. It still fits with ~2.4 GB headroom,
but it is worth monitoring before adding larger models.

Quality check at seed 4201 (baseline `_00001_` vs phase 1 `_00002_`):

- Z-Image: mean abs diff 0.023/255, max 1, no pixel >2.
- Krea2: mean abs diff 0.031/255, max 7, 0.007% pixels >2.
- Boogu: mean abs diff 0.027/255, max 2, no pixel >2.

Outputs are effectively identical. **Decision: keep `--fp16-vae` for now.**

## Phase 2 — xformers A/B (exploratory, rejected)

`xformers==0.0.28.post2` is built for **torch 2.5.0** and fails to load its
C++/CUDA extensions on the pinned torch 2.4.1. The correct torch-2.4.1 wheel is
**`xformers==0.0.28.post1`**. That wheel imports, loads its extensions, and
`memory_efficient_attention` succeeds on the P100 (`sm_60`).

ComfyUI log with post1: `Using xformers attention` and
`xformers version: 0.0.28.post1`.

| Workflow | Phase 1 SDPA | Phase 2 xformers | Delta |
|---|---:|---:|---:|
| z-image-turbo | 151.20 s | 151.24 s | +0.04 s (noise) |
| krea2-turbo | 118.36 s | 118.37 s | +0.01 s (noise) |
| boogu-turbo | 37.06 s | 37.06 s | 0.00 s |

3 measured runs each, all successful. Peak VRAM effectively unchanged. There is
no measurable benefit, so xformers was **uninstalled** and ComfyUI restarted.
Current log: `Using pytorch attention`; `import xformers` fails.

**Current state:** Phase 1 stack — `COMFYUI_ARGS=--fp16-vae`, `NORMAL_VRAM`,
SDPA, torch 2.4.1, no xformers.

## Phase 3.1 — Boogu Q5_0 GGUF vs fp8 (2026-11-03)

Downloaded `boogu-turbo-dit-Q5_0.gguf` (V1, 8.04 GB) and
`Boogu-Turbo-V2_dit-Q5_0.gguf` (V2/hotfix, 7.99 GB) from
`realrebelai/Boogu-Image-Turbo_GGUFs`. Added `UnetLoaderGGUF` workflow copies.
Harness: `phase3_boogu_gguf_results.json` (V2) and
`phase3_boogu_gguf_v1_results.json` (V1); logs alongside.

| Workflow | Phase 1 fp8 | Q5_0 GGUF (V1) | Delta | Peak VRAM |
|---|---:|---:|---:|---:|
| boogu-turbo | 37.05 s | **41.18 s** | +4.12 s (+11.1%) | 13,791 -> **11,585 MB** |

3 measured runs each (same seeds 4201-4203, 1 warm-up), all successful, no OOM.
The V2 GGUF gives the same timing (41.22 s) because it has the same tensor
structure/size.

### Quality

- fp8 vs **V1** Q5_0 GGUF (same model revision, same seeds): mean abs diff
  15.3-18.9/255, max ~239. Visually equivalent composition and detail; no
  black/NaN. The pixel delta is 5-bit quantization noise amplified by the
  4-step turbo sampler, not a visible quality regression.
- fp8 vs **V2** GGUF: mean abs diff 42-51/255. V2 is the **hotfix checkpoint**
  (Comfy-Org ships `boogu_image_turbo_hotfix_bf16/int8_convrot/nvfp4`, but no
  fp8), so this is a different model revision and not a valid quantization A/B.

**Decision:** keep `fp8_scaled` as the Boogu default (faster, fits with ~2.4 GB
headroom). Keep Q5_0 GGUF as a VRAM fallback only.

## Phase 3.2 — Krea2 Q5_K_M vs Q6_K (2026-11-03, LoRA check 2026-11-04)

Downloaded `krea2_turbo-Q5_K_M.gguf` (8.87 GB) from
`vantagewithai/Krea-2-Turbo-GGUF` (the same repo as the current Q6_K). Harness:
`phase3_krea2_q5km_results.json`.

| Workflow | Q6_K | Q5_K_M | Delta | Peak VRAM |
|---|---:|---:|---:|---:|
| krea2-turbo | 118.62 s | **118.15 s** | -0.47 s (-0.4%, noise) | 12,641 -> **11,265 MB** |

3 measured runs each (seeds 4201-4203, 1 warm-up), all successful, no OOM.
Quality at the same seeds: mean abs diff 5.1-12.8/255, max 227; visually
equivalent composition/detail, no black/NaN.

### Identity-edit LoRA validation

The concern was that quantization could degrade the identity-edit LoRA. Ran
`Image1_krea2_edit` (same input `S__42058016.jpg`, same seeds 4201/4202) with
both UNETs. Harness: `phase3_krea2_edit_results.json` (Q6_K) and
`phase3_krea2_edit_q5km_console.log` (Q5_K_M; the results JSON was lost when
the harness was killed after the last run, timings below are from the log).

| Edit workflow | Q6_K | Q5_K_M | Delta | Peak VRAM |
|---|---:|---:|---:|---:|
| krea2-identity-edit | 396.5 s | **395.8 s** | -0.7 s (-0.2%, noise) | 14,529 -> **12,993 MB** |

Same-seed image diff: mean abs 3.7-4.1/255, max 246; faces/identities and
scene preserved, visually equivalent, no black/NaN. Identical LoRA strength
and sampler settings.

**Decision: adopt `Q5_K_M` as the Krea2 default.** Same speed, -1.4 GB on T2I
and -1.5 GB on identity edit, visually equivalent output including the LoRA.
Updated all llmMobile API workflows and the matching ComfyUI UI workflows;
`Q6_K` is now an optional fallback only.

## Phase 3.3 — Z-Image GGUF vs bf16 (2026-11-03)

Downloaded `z_image_turbo-Q8_0.gguf` (7.22 GB) and `Q6_K.gguf` (5.91 GB) from
`vantagewithai/Z-Image-Turbo-GGUF`. Harness: `phase3_zimage_gguf_results.json`.

| Workflow | bf16 | Q8_0 | Q6_K |
|---|---:|---:|---:|
| z-image-turbo | **151.21 s** | 150.80 s | 154.20 s |
| Peak VRAM | 14,505 MB | 14,751 MB | 13,825 MB |

3 measured runs each (seeds 4201-4203, 1 warm-up), all successful.
Quality: no NaNs/black images; Q8_0 mean abs diff 2.97/255, Q6_K 7.0/255;
visually equivalent.

**Decision: reject GGUF for Z-Image.** On the P100 the model runs FP32 compute
(bf16 weights, manual cast to fp32), so a smaller GGUF file does not translate
into the expected VRAM saving; Q8_0 is neutral, Q6_K only frees 680 MB and is
2% slower due to dequantization. Keep the bf16 safetensors.

## Phase 3.4 — Text-encoder cost (2026-11-03)

Added `profile_nodes.py`, which subscribes to ComfyUI's websocket events and
derives node time from consecutive `executing` messages. A warm-up is followed
by a profiled run with a **different prompt**, so `CLIPTextEncode` is not
cache-skipped. Raw data: `phase3_node_profiles.json` (cold) and
`phase3_node_profiles_warm.json` (warm); logs alongside.

Warm profiled run (fresh prompt):

| Workflow | CLIPTextEncode | KSampler | Other | Real-prompt total | Cached-prompt total |
|---|---:|---:|---:|---:|---:|
| z-image-turbo | **3.26 s** | 146.65 s | 4.44 s | ~154.4 s | 151.2 s |
| krea2-turbo | **6.44 s** | 117.26 s | 0.88 s | ~124.6 s | 118.4 s |
| boogu-turbo | **13.78 s** | 35.61 s | 0.99 s | ~50.4 s | 37.1 s |

Cold loader costs (first run): Z-Image UNETLoader 10.6 s + CLIPLoader 3.9 s;
Krea2 CLIPLoader 3.8 s; Boogu CLIPLoader 5.5 s. Boogu's cold KSampler is ~126 s
because the fp8 DiT weight load is deferred into the sampler node.

### Important benchmark caveat

The main harness reuses one identical prompt for every run, so ComfyUI caches
`CLIPTextEncode` and skips it in measured runs. The cached-prompt numbers above
therefore understate real new-prompt latency by ~3.3 s (Z-Image), ~6.2 s
(Krea2), and ~13.3 s (Boogu). A/B comparisons remain valid because both sides
are measured the same way, but absolute per-image latency is higher in
production when prompts change.

**Decision: no text-encoder change.** Boogu's 8B encoder (10.6 GB) cannot stay
resident alongside even the Q5 DiT (8.0 GB) in 16 GB, so the swap cost is
unavoidable. Krea2/Z-Image encoder time is small. GGUF text encoders were not
tried: the Boogu model card requires the FP8 Qwen3-VL encoder.

## Phase 3 summary

One model-format change was adopted; everything else stays on the Phase 1
stack:

- Z-Image: bf16 safetensors, 151.2 s cached / ~154.4 s real
- Krea2: **Q5_K_M** (adopted), 118.2 s cached / ~124.4 s real; edit 395.8 s
- Boogu: fp8_scaled, 37.1 s cached / ~50.4 s real

Useful fallback (not default): Boogu Q5_0 GGUF (-2.2 GB, +11% time). Z-Image
GGUF is not useful on this GPU. The rejected GGUF test files (Z-Image Q8/Q6_K,
Boogu V1/V2, Krea2 Q6_K) and their test workflows were deleted on 2026-11-04,
freeing ~37 GiB; see TODO §11.

## Next benchmark

Phase 4 optional items: the known-good pre-freeze stack (torch 2.5.1 +
xformers 0.0.29) A/B, `--fast autotune`, and GPU persistence/clock checks.

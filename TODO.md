# Tesla P100 ComfyUI Speed Optimization TODO

Status: **Phases 1-3 complete.** `--fp16-vae` kept; xformers tested and removed
(no gain). Phase 3 outcome: **Krea2 Q5_K_M adopted** (speed tie, -1.4/-1.5 GB
VRAM, identity-edit LoRA validated); Boogu Q5_0 rejected as default (11%
slower, kept as fallback); Z-Image GGUF rejected. Next: Phase 4 optional items.
Reference: `tesla_p100_comfyui_optimization_plan.md`

---

## 1. Verified current setup (2026-11-02)

| Item | Current state |
|---|---|
| GPU 0 | Tesla P100-PCIE-16GB, `sm_60`, 16 GB HBM2, driver 580 / CUDA 13 capable |
| GPU 1 | GTX 1060 6GB, used by `llm-server-mini`; not a viable ComfyUI worker |
| ComfyUI container | `comfyui` is **running** (started through llmMobile) |
| Image | `ghcr.io/ai-dock/comfyui:latest-cuda` |
| ComfyUI core | frozen at commit `68806143` (see `update.sh`) |
| PyTorch | `2.4.1+cu121` |
| Attention | native PyTorch SDPA; **xformers was tested and removed** (no gain) |
| Launch args | `COMFYUI_ARGS=--fp16-vae` (applied: process args and `/etc/comfyui_args.conf`) |
| VRAM mode | `NORMAL_VRAM`; `--lowvram` is intentionally not used |
| Allocator | `garbage_collection_threshold:0.8,max_split_size_mb:64` |
| System RAM | 32 GB |

### Current workflows (from `~/dev/llmMobile`)

| Workflow | Diffusion model | Text encoder | Typical resolution / steps |
|---|---|---|---|
| `z-image-turbo` | `z_image_turbo_bf16.safetensors` (12.3 GB) | `qwen_3_4b.safetensors` (8.0 GB) | 1920x1088 / 8 |
| `krea2-turbo` | `krea2_turbo-Q5_K_M.gguf` (8.9 GB) | `qwen3vl_4b_fp8_scaled.safetensors` (5.2 GB) | 1280x720 / 8 |
| `boogu-turbo` | `boogu_image_turbo_fp8_scaled.safetensors` (10.3 GB) | `qwen3vl_8b_fp8_scaled.safetensors` (10.6 GB) | 720x1280 / 4 |
| `krea2-edit` | `krea2_turbo-Q5_K_M.gguf` + LoRA | `qwen3vl_4b_fp8_scaled.safetensors` | source resolution / 10 |

### Existing reference timings (old logs, **not** a clean baseline)

These are from `ComfyUI/comfyui_detail.log` during the pre-freeze state
(`NORMAL_VRAM` + xformers + torch 2.5.1). They are useful as a target, not as the
current baseline:

- Boogu T2I, 4 steps, 720x1280: **~48–53 s** total; sampler ~27 s.
- Z-Image Turbo, 8 steps: **~90 s** total at **1280x720** (latent 160x90);
  DiT load ~13 s, sampling ~46 s. The current workflow is **1920x1088**
  (2.27x the pixels), so the current 151 s is not a regression.
- Krea2: no clean timing captured yet.

Current measured baseline (`NORMAL_VRAM`, no args, SDPA, torch 2.4.1) and
Phase 1 (`--fp16-vae`):

| Workflow | Baseline | Phase 1 | Peak VRAM (P1) |
|---|---:|---:|---:|
| Z-Image | 153.2 s | **151.2 s** | 14,505 MB |
| Krea2 | 120.2 s | **118.4 s** | 12,705 MB |
| Boogu | 38.6 s | **37.1 s** | 13,921 MB |

See `BENCHMARKS.md` for methodology and raw data.

---

## 2. Corrections to the supplied plan (important)

These are hardware facts that change the order of the roadmap:

1. **Do not start with `--force-fp32`.**
   The P100 is GP100, not a consumer Pascal card. It has native FP16 at roughly
   **2x FP32** throughput (about 18.7 vs 9.3 TFLOPS), and it does **not** have
   native BF16/FP8. Forcing FP32 will roughly double model memory and usually
   make sampling slower. The real dtype problem is BF16/FP8 emulation, not FP16.

2. **SageAttention is not viable on `sm_60`.**
   SageAttention/2/2++ kernels target `sm_80+` (Ampere/Ada/Hopper) and INT8/FP8
   tensor cores. The P100 has none of those. Do not spend time on the
   `ComfyUI-SageAttention` phase unless a `sm_60`-specific fork is proven to work.

3. **GGUF is already partially deployed.**
   Krea2 already runs a GGUF UNET through `ComfyUI-GGUF`. The useful next step
   is extending GGUF to other models, not installing the node.

4. **The configured launch flags were never active.**
   This ai-dock image reads `COMFYUI_ARGS`; compose set `ARGS`. The baseline
   therefore ran with no args (`NORMAL_VRAM`, no `--fp16-vae`). That baseline
   already proved Boogu fits without `--lowvram` (11.97 GB peak), so the old
   "Boogu needs global lowvram" assumption is unsupported. Fixed in Phase 1;
   do not re-add `--lowvram` without evidence.

5. **Do not upgrade PyTorch past 2.5.x.**
   Torch 2.7+ drops `sm_60`; the current 2.4.1 pin is intentional. The
   pre-freeze logs show torch **2.5.1** + xformers 0.0.29 also worked on this P100.

6. **Do not upgrade ComfyUI past `68806143`.**
   The next attention rewrite (`b481bc15`) materializes the full attention matrix
   on the math backend and OOMs Boogu at 16 GB.

7. **Multi-P100 phase 4 does not apply.**
   There is one P100. The GTX 1060 has 6 GB and is already assigned to
   `llm-server-mini`. `ComfyUI-ParallelAnything` is out of scope.

---

## 3. Priority order

| Order | Optimization | Expected gain | Risk | Downloads |
|---|---|---|---|---|
| 0 | Baseline harness | measurement only | none | none |
| **1** | **Fix launch-arg plumbing (`COMFYUI_ARGS=--fp16-vae`), keep NORMAL_VRAM** | **low** (VAE only; baseline already has no lowvram) | low (quality/precision) | none |
| 2 | Attention A/B: xformers vs SDPA | **none measured** (post1 works but timings are identical) | low (reversible) | tested, reverted |
| 3 | GGUF/dtype tuning: Boogu Q5_0, Krea2 Q5_K_M, text-encoder placement | medium (VRAM/bandwidth) | medium (quality change) | model files |
| 4 | Optional: torch 2.5.1 + xformers 0.0.29 (known-good pre-freeze combo) | medium | medium (re-freeze needed) | pip wheels |
| — | `--force-fp32`, SageAttention, ParallelAnything | negative / unsupported | high | none |

---

## 4. Phase 0 — Baseline harness (do this first, no behavior change)

- [x] Confirm no LLM is occupying GPU 0 (`nvidia-smi`).
- [x] Start ComfyUI with the current frozen config.
- [x] Create `bench_workflows.py`; 1 warm-up + 3 measured runs per workflow,
      varied seeds, liveness/keepalive checks, wall/exec time and peak VRAM.
- [x] Measure the current state. Result: no launch args were active; logs show
      `NORMAL_VRAM`, SDPA, torch 2.4.1, no xformers.
- [x] Save raw data (`baseline_results.json`), console log, and `BENCHMARKS.md`.
- [x] Repeated runs are stable: z-image and krea2 within 0.03%; Boogu within 0.9%.

**Acceptance:** met — reproducible baseline in `BENCHMARKS.md`.

Note: per-sampler-step timing was not captured because the detail logger from the
old stack is not writing under the current container. Total execution time is
stable enough for A/B comparisons; add sampler timing only if a difference needs
explaining.

---

## 5. Phase 1 — FIRST OPTIMIZATION: memory / launch profile

**Why first:** it is a one-line config fix, needs no downloads, and makes the
launch profile honest. The baseline already ran on `NORMAL_VRAM`, so this phase
isolates the only intended flag that was missing: `--fp16-vae`.

- [x] Change only `docker-compose.yml`:
  `ARGS=--fp16-vae --lowvram` -> `COMFYUI_ARGS=--fp16-vae`
- [x] Recreate the container (`docker compose up -d --force-recreate`).
- [x] Verify the flag actually applied: process args and
  `/etc/comfyui_args.conf` contain `--fp16-vae`; log still says `NORMAL_VRAM`.
- [x] Benchmark z-image, krea2, and boogu. Results:
  - z-image 153.20 -> **151.20 s** (-1.3%)
  - krea2 120.16 -> **118.36 s** (-1.5%)
  - boogu 38.60 -> **37.06 s** (-4.0%)
- [x] Quality check at the same seed: mean abs diff <= 0.03/255, max 7.
- [x] Keep `--fp16-vae`. Note Boogu peak VRAM rose 11.97 -> 13.92 GB; watch it.
- [x] Do **not** add `--lowvram` back: Boogu already completed at 11.97 GB peak
  on `NORMAL_VRAM`. Only revisit if a future model change causes an actual OOM.
- [x] No OOM observed; allocator variants not needed. Keep the current
  `max_split_size_mb:64` control.
- [x] Did **not** add `--force-fp32`, `--highvram`, or `--cache-none`.

**Acceptance:** met — intended args applied, all three workflows pass on
`NORMAL_VRAM`, no OOM, `--fp16-vae` kept (outputs match baseline).

---

## 6. Phase 2 — Attention backend A/B (substitute for SageAttention)

**Result: rejected.** xformers works on `sm_60`, but it is not faster for these
workflows. Removed to keep the stack simple.

- [x] Wheel compatibility: `xformers==0.0.28.post2` is built for **torch 2.5.0**
  and fails to load its C++/CUDA extensions on torch 2.4.1. The correct wheel is
  **`xformers==0.0.28.post1`** (requires torch 2.4.1).
- [x] Installed post1. `memory_efficient_attention` succeeded on the P100 and
  ComfyUI logged `Using xformers attention`.
- [x] Benchmarked all three workflows with xformers (and `--fp16-vae`):
  - Z-Image: 151.24 s (Phase 1 SDPA: 151.20 s)
  - Krea2: 118.37 s (Phase 1 SDPA: 118.36 s)
  - Boogu: 37.06 s (Phase 1 SDPA: 37.06 s)
- [x] No gain, so uninstalled xformers and restarted. Current log:
  `Using pytorch attention`; `import xformers` fails.
- [x] `update.sh` unchanged: it already uninstalls xformers.
- [x] Optional microbenchmark skipped: end-to-end already shows no difference.

**Acceptance:** met — SDPA kept, no workflow regressed, no xformers dependency.

Note: the older ~90 s Z-Image log was **1280x720**, not the current 1920x1088.
The current SDPA time is consistent with the pixel count, so xformers was not
the missing 60 s.

---

## 7. Phase 3 — Model format / quantization tuning

**Why third:** this is the largest memory/bandwidth lever, but it is download-
and quality-sensitive, so it comes after the free launch/attention wins.

### 7.1 Boogu (tested 2026-11-03: keep fp8, GGUF only as VRAM fallback)

- [x] Downloaded both `Boogu-Turbo-V2_dit-Q5_0.gguf` (8.0 GB) and
  `boogu-turbo-dit-Q5_0.gguf` (8.0 GB) from
  `realrebelai/Boogu-Image-Turbo_GGUFs` into `ComfyUI/models/unet/`.
- [x] Added GGUF workflow copies using `UnetLoaderGGUF`
  (`My_Boogu_Image_Turbo_GGUF.json`, `My_Boogu_Image_Turbo_GGUF_V1.json`).
- [x] Benchmarked Q5_0 vs `fp8_scaled` at the same seeds (4201-4203):
  - fp8: **37.05 s**, peak **13,791 MB**
  - Q5_0 GGUF: **41.18 s**, peak **11,585 MB**
  - Delta: **+4.12 s (+11.1%) slower**, **-2.2 GB (-16%) VRAM**.
- [x] Quality (fp8 vs V1 Q5_0, same seed): mean abs diff 15.3-18.9/255,
  max ~239, but visually equivalent composition/detail; no black/NaN. The
  large pixel delta is expected from 5-bit quantization amplified by 4-step
  turbo sampling.
- [x] Important: the "V2" GGUF is the **hotfix checkpoint**, not the same
  weights as the current fp8 (Comfy-Org has `hotfix` bf16/int8/nvfp4, no fp8).
  Its large pixel delta (mean 42-51) reflects a different model revision, so
  only the V1 GGUF is a valid quantization A/B.
- [x] **Decision: keep `fp8_scaled` as the default** (faster and still fits).
  Keep the Q5_0 GGUF as a fallback only if VRAM headroom is needed.
- [x] Keep the fp8 workflow as a fallback.

### 7.2 Krea2 (done 2026-11-04: Q5_K_M adopted, -1.4 to -1.5 GB VRAM)

- [x] Downloaded `krea2_turbo-Q5_K_M.gguf` (8.87 GB) from
  `vantagewithai/Krea-2-Turbo-GGUF` (same source as the old Q6_K).
- [x] T2I benchmark vs `Q6_K` at the same seeds (4201-4203):
  - Q6_K: **118.62 s**, peak **12,641 MB**
  - Q5_K_M: **118.15 s**, peak **11,265 MB**
  - Delta: **-0.47 s (-0.4%, noise)**, **-1.38 GB (-10.9%) VRAM**.
- [x] Quality (same seed): mean abs diff 5.1-12.8/255, max 227; visually
  equivalent composition/detail; no black/NaN.
- [x] Keeping the 4B text encoder on GPU is not the bottleneck: its encode is
  only ~6.4 s warm, and ComfyUI already manages residency. No end-to-end gain.
- [x] **Identity-edit LoRA validated** (`Image1_krea2_edit`, same input/seed):
  - Q6_K: **396.5 s**, peak **14,529 MB**
  - Q5_K_M: **395.8 s**, peak **12,993 MB** (-1.54 GB)
  - Quality: mean abs diff 3.7-4.1/255, max 246; faces/identities preserved,
    output visually equivalent. No black/NaN.
- [x] **Adopted `Q5_K_M` as the Krea2 default** in all llmMobile API workflows
  (T2I, Image1 edit, Img2-to-Img1 edit) and in the matching ComfyUI UI
  workflows. `Q6_K` kept only as an optional fallback.

### 7.3 Z-Image (tested 2026-11-03: GGUF rejected)

- [x] Did **not** switch to FP16 (known NaN/black-image issue); P100 still
  upcasts BF16 to FP32.
- [x] Downloaded `z_image_turbo-Q8_0.gguf` (7.22 GB) and `Q6_K.gguf` (5.91 GB)
  from `vantagewithai/Z-Image-Turbo-GGUF` and benchmarked at the same seeds:
  - bf16: **151.21 s**, peak **14,505 MB**
  - Q8_0: **150.80 s**, peak **14,751 MB** (no gain; slightly more VRAM)
  - Q6_K: **154.20 s**, peak **13,825 MB** (+2.0% slower; only -680 MB)
- [x] Quality: no NaNs/black images; Q8_0 mean abs diff 2.97/255, Q6_K 7.0/255;
  visually equivalent.
- [x] **Decision: reject GGUF for Z-Image.** On the P100 the model runs as FP32
  compute, so GGUF dequantization does not produce the file-size VRAM saving;
  Q6_K just adds dequant overhead. Keep the bf16 safetensors.
- [x] Did not use `int8_convrot`/`nvfp4` variants (require newer
  comfy-kitchen/CUDA paths unavailable on this stack).

### 7.4 Text encoders (measured 2026-11-03: no change)

- [x] Measured per-node time with a websocket profiler (`profile_nodes.py`),
  warm run with a fresh prompt so the encoder is not cache-skipped:
  - Z-Image: `CLIPTextEncode` **3.26 s**, KSampler 146.65 s (~154 s real total)
  - Krea2: `CLIPTextEncode` **6.44 s**, KSampler 117.26 s (~125 s real total)
  - Boogu: `CLIPTextEncode` **13.78 s**, KSampler 35.61 s (~50 s real total)
- [x] Cold loader costs: Z-Image UNETLoader 10.6 s + CLIPLoader 3.9 s; Boogu
  CLIPLoader 5.5 s (cold KSampler includes deferred DiT load, ~126 s).
- [x] **Found a benchmark caveat:** the harness reuses an identical prompt, so
  ComfyUI caches `CLIPTextEncode`; measured totals understate real new-prompt
  latency by ~3.3 s (Z-Image), ~6.2 s (Krea2), ~13.3 s (Boogu).
- [x] Keeping the encoder on GPU is infeasible for Boogu: 8B TE (10.6 GB) plus
  even the Q5 DiT (8.0 GB) exceeds 16 GB. Krea2/Z-Image encoder time is small.
- [x] Did not try GGUF text encoders: the Boogu model card requires the FP8
  Qwen3-VL encoder; quality/loader support is not established.
- [x] No text-encoder change made.

**Acceptance:** met — every Phase 3 change has before/after time, VRAM figure,
and a same-seed visual check; no black images or NaNs.

---

## 8. Phase 4 — Optional / deferred

- [ ] Optional: A/B the known-good pre-freeze stack
  (torch 2.5.1 + xformers 0.0.29.post1 + default VRAM) if Phase 2 is inconclusive.
- [ ] Optional: test `--fast autotune` in isolation; expect limited/no benefit on
  `sm_60`, revert on any crash.
- [ ] Optional: `nvidia-smi -pm 1` and confirm the P100 is not power/clock capped.
- [ ] Deferred: 64 GB system RAM. This helps CPU offload under `--lowvram`, but it
  is a hardware purchase and should follow the software wins.
- [ ] Skip: SageAttention, `--force-fp32`, multi-GPU parallelism, ComfyUI/torch
  upgrades that drop `sm_60`.

---

## 9. Rollback plan

- Keep the repo clean before each experiment and record `git diff`.
- Compose changes: `git checkout -- docker-compose.yml` then
  `docker compose up -d --force-recreate`.
- Venv changes: `pip uninstall -y xformers`; `./update.sh` restores the pinned
  torch/comfy-kitchen state.
- Workflow changes: keep the original JSONs in `~/dev/llmMobile`; only add new
  files or edit copies until a change is proven.
- Revert `update.sh` if xformers is not adopted.

---

## 10. Decision log

| Date | Change | z-image | krea2 | boogu | Result |
|---|---|---|---|---|---|
| 2026-11-02 | Baseline: no args active, `NORMAL_VRAM`, SDPA, torch 2.4.1 | 153.2 s | 120.2 s | 38.6 s | **reference**; flags `ARGS` were ignored |
| 2026-11-02 | Phase 1: `COMFYUI_ARGS=--fp16-vae`, `NORMAL_VRAM` | 151.2 s | 118.4 s | 37.1 s | **kept**; outputs match baseline, Boogu VRAM +1.95 GB |
| 2026-11-02 | Phase 2: xformers 0.0.28.post1 + SDPA A/B | 151.24 s | 118.37 s | 37.06 s | **no gain; reverted** to SDPA |
| 2026-11-03 | Phase 3.1: Boogu Q5_0 GGUF (V1) vs fp8 | — | — | 41.18 s (fp8 37.05 s) | **no speed win**; -2.2 GB VRAM; keep fp8 default, GGUF as fallback |
| 2026-11-03 | Phase 3.2: Krea2 Q5_K_M vs Q6_K | — | 118.15 s (Q6_K 118.62 s) | — | **tie**; -1.38 GB VRAM |
| 2026-11-04 | Phase 3.2: identity-edit LoRA Q6_K vs Q5_K_M | — | 395.8 s (Q6_K 396.5 s) | — | **adopted Q5_K_M**; -1.54 GB VRAM, diff 3.7-4.1/255, faces preserved |
| 2026-11-03 | Phase 3.3: Z-Image Q8_0 / Q6_K GGUF vs bf16 | 150.80 / 154.20 s (bf16 151.21 s) | — | — | **rejected**; no VRAM win, Q6_K slower |
| 2026-11-03 | Phase 3.4: text-encoder profiling | TE 3.3 s | TE 6.4 s | TE 13.8 s | **no change**; Boogu 8B TE cannot stay on GPU |
| | | | | | **Phase 3 complete; Krea2 Q5_K_M adopted** |

---

## 11. Model files removed (2026-11-04)

All five rejected/obsolete weight files were deleted, together with the test
workflows that referenced them. Free space went from ~55 GB to ~91 GB
(**~37 GiB freed**). `krea2_turbo-Q5_K_M.gguf` is now the only UNET GGUF left.

| File | Size | Reason |
|---|---:|---|
| `models/unet/z_image_turbo-Q8_0.gguf` | 7.22 GB | Z-Image GGUF rejected (neutral vs bf16); test-only |
| `models/unet/z_image_turbo-Q6_K.gguf` | 5.91 GB | Z-Image GGUF rejected (2% slower, only 680 MB saved); test-only |
| `models/unet/Boogu-Turbo-V2_dit-Q5_0.gguf` | 7.99 GB | V2 hotfix is a different checkpoint revision, not adopted; test-only |
| `models/unet/boogu-turbo-dit-Q5_0.gguf` | 8.04 GB | V1 GGUF was only a VRAM fallback (+11% time) |
| `models/unet/krea2_turbo-Q6_K.gguf` | 10.58 GB | Old default, replaced by Q5_K_M |

Deleted with them: `MyZimage_turbo_GGUF_{Q8,Q6K}.json`,
`My_Boogu_Image_Turbo_GGUF{,_V1}.json`, and the duplicate
`MyKrea2E_Turbo_Q5KM.json` / `Image1_krea2_edit_Q5KM.json`. Do not remove:
`krea2_turbo-Q5_K_M`, `boogu_image_turbo_fp8_scaled`, `z_image_turbo_bf16`, the
three text encoders, the two VAEs, `krea2_identity_edit_v1_2` (active edit
LoRA), or `krea2_sunsetblur` (used by `My_krea2_turbo_t2i.json`).

# ComfyUI on Tesla P100 + MiniMax H3 — Research Findings

**Date:** 2026-11-17
**Hardware context:** NVIDIA Tesla P100 16 GB (GP100, compute capability **6.0 / sm_60**), ComfyUI in a container.
**Goal investigated:** Can we run the MiniMax H3 video-generation workflow on our ComfyUI?

---

## TL;DR

- **"Frozen ComfyUI" is a misdiagnosis.** The thing that broke Pascal cards is **PyTorch/CUDA**, not ComfyUI. We can run *current* ComfyUI on the P100 by pinning the right PyTorch wheel (sm_60). No fork strictly required.
- **MiniMax H3 has two distinct paths in ComfyUI:**
  - **Path A — Cloud API nodes** (`MinimaxHailuo03*`): job goes to MiniMax cloud, returns MP4. **No local GPU involved.** Works today on current ComfyUI (needs 0.30+). This is the practical route.
  - **Path B — Local open-weights:** possible but painful. Runs via dynamic VRAM offloading; bottleneck is **system RAM + PCIe**, not VRAM. Expect short low-res clips in single-to-double-digit minutes, with a P100-specific fp16 patch helping ~2×. Not an interactive workflow.
- For genuinely *local* video on this card, **Wan 2.1/2.2** is the realistic choice (proven ~5 min per 5 s clip on a P100).

---

## 1) ComfyUI + P100: it's PyTorch, not ComfyUI

NVIDIA dropped Pascal (sm_60/sm_61) in **CUDA 12.9+**. Newer PyTorch ships that CUDA → the classic
`no kernel image is available for execution on the device`. This is why "new ComfyUI" appeared to stop working; it was really the PyTorch wheel underneath.

**P100 is sm_60, NOT sm_61.** GTX 10-series and P40 are sm_61. A lot of generic "Pascal" advice is wrong for the P100 specifically:
- P100 has **full-rate (double-rate) vector fp16** but **no fast int8 (dp4a)** dot product → opposite profile to P40/GTX 10.
- Measured on a real P100: **fp32 maths is ~11% faster than fp16 end-to-end** for diffusion here. Leave precision at ComfyUI's default (fp32); do NOT force `--fp16-unet`/`--force-fp16`.
- No native bf16 / fp8 / int8 hardware → those quantized model files fall back to float (slower, more memory).

### Working sm_60 configurations (proven)
- **cu126 wheels** — Linux, proven. One P100 user runs **ComfyUI 0.39 + PyTorch 2.14 + cu126** in Docker doing images *and* video.
- **cu118** — `pip install torch==2.7.1+cu118 torchaudio==2.7.1+cu118 --index-url download.pytorch.org/whl/cu118`.
- **Self-built sm_60 wheel** — CUDA 12.x + cuDNN 8.9, `TORCH_CUDA_ARCH_LIST="6.0"`.

Verify after install:
```bash
python -c "import torch; print(torch.__version__, torch.version.cuda, torch.backends.cudnn.version(), torch.cuda.get_arch_list())"
# arch list MUST include sm_60
```

### P100-specific launch settings (measured)
- `TORCH_DISABLE_NATIVE_JIT=1` — newer PyTorch tries to JIT a Triton kernel and fails without a C compiler in the image.
- Precision: default **fp32** (do not force fp16).
- `int8_convrot` model files need a one-line patch to convert to float on Pascal (no int8 matmul in cuBLASLt); nvfp4/fp8 fall back to float automatically.
- Start ComfyUI with **`--fast-disk`** — without it, one process can eat ~12 GB of host RAM.
- Driver: stay on branch **580 proprietary**. The open kernel modules do NOT support Pascal. 580 is the last Maxwell/Pascal/Volta branch (supported to mid-2028).

### Turnkey options if we don't want to manage the wheel ourselves
- `comfyorg/comfyui` portable build: "pytorch cuda 12.6 — supports Nvidia 10 series and older GPUs".
- `hiddenswitch/ComfyUI` (LTS fork, pip/uv installable) with `--torch-backend=auto`.
- **Best reference repo:** [`4claps/tesla-p100-comfyui-imagegen`](https://github.com/4claps/tesla-p100-comfyui-imagegen) — full Docker setup proven on P100s, includes video (Wan 2.1/2.2). Has `Dockerfile.p100` + `patch_int8.py` with the two P100 fixes (JIT switch, INT8 fallback), and a `compose.yml` running one ComfyUI instance per card on ports 8188–8191.

### Measured P100 performance (from that repo, for calibration)
- FLUX.2 klein: good 1024×1024 image in **~25 s**/card.
- Z-Image Turbo (int8 file): ~80 s/image, best text rendering.
- Video (Wan 2.1 / Wan 2.2 5B): **~5 min per 5 s clip** on one card at 175 W cap.
- Cold start from spinning disk: 4–9 min to read models in (~80 MB/s).

---

## 2) MiniMax H3 in ComfyUI — two paths

MiniMax H3 is an open-weights omni-modal video model (text/image/video/audio in → video with **native stereo audio**). Native 768p short edge, up to ~15 s at 24 fps. ComfyUI has had native support since **v0.30.0** (T2V / I2V / R2V templates + built-in nodes).

### Path A — Cloud API nodes (the practical one)
- Built-in nodes: `MinimaxHailuo03TextToVideoNode`, `...ImageToVideoNode`, `...FirstLastFrameNode` (+ R2V). Category `partner/video/MiniMax`.
- The node sends the request to MiniMax's cloud, polls, downloads and returns a finished MP4. **No local GPU used.** P100 is irrelevant — works on any current ComfyUI install (needs 0.30+ for the nodes).
- Cost = Comfy/MiniMax API key + per-generation credits (e.g. ~$0.1287/s @768p, $0.1859/s @2K, computed in-node).
- ⚠️ **Licensing:** as of the license revision reviewed 2026-08-26, **US / EU / UK / South Korea are "Excluded Territories"** under the MiniMax H3 Community License and require a separate commercial license. Comfy Cloud generations already include commercial rights. Confirm our region before relying on this commercially.

### Path B — Local open-weights on the P100 (possible, painful)
Model is large:
- Pruned INT8 video transformer ~**21 GB**; Qwen3-VL-32B text encoder ~**15.7–27 GB** (NVFP4 15.7 / INT8 27.1); VAEs ~6 GB. Full BF16 ≈ **124 GB**.
- Runs on small cards only via ComfyUI's **dynamic VRAM offloading** — streaming weights from system RAM every step.

Key facts:
- **The bottleneck is system RAM + PCIe, not VRAM.** A 16 GB-VRAM run froze at 32 GB host RAM and needed 64 GB. Plan for **32 GB min, 64 GB ideal**.
- P100 twist: no bf16/fp8/int8 → all quantized H3 files fall back to fp32 (slower + more memory).
- **P100-specific patch:** [`Amduraznak/minimax-h3-fp16-fix`](https://github.com/Amduraznak/minimax-h3-fp16-fix) enables native fp16 on exactly this card class. H3 declares `supported_inference_dtypes = [bf16, fp32]`, so without the patch ComfyUI silently falls back to fp32 manual-cast (and `--fp16-unet` alone → black frames). The patch makes native fp16 work with exact math: **~11× on V100**, and explicitly notes **"P100: ~2x expected. No tensor cores, but double-rate vector fp16."** (P40/GTX 10 sm_61: "don't bother" — 1/64 rate.) Install by copying `minimax_h3_fp16_fix.py` into `ComfyUI/custom_nodes/`, launch with `--fp16-unet`.
- Pascal-capable launcher reference: [`yume-arasaki/ezlaunch-minimax-h3`](https://github.com/yume-arasaki/ezlaunch-minimax-h3) — lists an **8 GB Pascal (GTX 10)** profile: `--lowvram` stack, no Sage, cu126 torch, ~55 min for a 5 s @480p clip. P100 (more VRAM + HBM2 bandwidth + double-rate fp16) should do better than that floor.

Realistic expectation on the P100: short low-res clips in single-to-double-digit minutes with the fp16 patch + offloading flags + big RAM; 768p / 15 s will be very long. Treat as batch/offline proof-of-concept, not an interactive workflow.

---

## Bottom line / recommendation

1. **Unfreeze ComfyUI:** update to current ComfyUI and pin PyTorch to an sm_60 build (cu126 or cu118) + the P100 flags above (`TORCH_DISABLE_NATIVE_JIT=1`, fp32 default, `--fast-disk`). No fork strictly required.
2. **For H3 video "in ComfyUI":** Path A (cloud API nodes) is the sane route — works today on current ComfyUI, P100 irrelevant, best quality/speed per effort. Confirm licensing for our region first.
3. **If it must be local:** short low-res clips via offloading + `minimax-h3-fp16-fix`, 64 GB RAM recommended. For genuinely local video on a P100, prefer **Wan 2.1/2.2** (proven ~5 min per 5 s clip).

---

## Sources
- ComfyUI system requirements — https://docs.comfy.org/installation/system_requirements
- ComfyUI "Which GPU should I buy" wiki (Pascal = fp32 only) — https://github.com/Comfy-Org/ComfyUI/wiki/Which-GPU-should-I-buy-for-ComfyUI
- `4claps/tesla-p100-comfyui-imagegen` (README, RESEARCH.md, RESULTS.md) — https://github.com/4claps/tesla-p100-comfyui-imagegen
- Comfy-Org/desktop issue #1300 "Pytorch support for Pascal GPUs" — https://github.com/comfy-org/desktop/issues/1300
- `X1000QAQ/pascal-torch-cuda-build` (self-built sm_6x wheel) — https://github.com/X1000QAQ/pascal-torch-cuda-build
- Low Budget Lab, "CUDA 13 and PyTorch dropped the P100: what still works" — https://lowbudgetlab.com/posts/p100-software-2026/
- MiniMax H3 ComfyUI guide — https://docs.comfy.org/tutorials/video/minimax/minimax-h3
- MiniMax "Run and self-host MiniMax H3" (SGLang baseline, licensing) — https://platform.minimax.io/docs/guides/local-deploy-h3
- Comfy-Org/MiniMax-H3 model repo — https://huggingface.co/Comfy-Org/MiniMax-H3
- `Amduraznak/minimax-h3-fp16-fix` (P100/Volta fp16 patch) — https://github.com/Amduraznak/minimax-h3-fp16-fix
- `yume-arasaki/ezlaunch-minimax-h3` (per-card-class profiles incl. Pascal 8 GB) — https://github.com/yume-arasaki/ezlaunch-minimax-h3
- Community H3 VRAM reports: openclawdc.com, minimax3.org, minimax-h3ai.video, modelvram.com, KingsClaw "From 118GB to 12GB", MiniMaxAI HF discussion #104.

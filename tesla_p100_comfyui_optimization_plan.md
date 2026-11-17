# Tesla P100 (Pascal `sm_60`) ComfyUI Optimization Guide

This document outlines a phased roadmap to maximize performance and memory efficiency when running ComfyUI on an Nvidia Tesla P100 (16GB HBM2). 

Because Pascal GPUs lack Tensor Cores and perform FP16 math at half the speed of FP32, standard ComfyUI configurations encounter severe bottlenecks. This guide tunes the backend, memory flags, attention mechanisms, and model formats to overcome those hardware limitations.

---

## Phase 1: Launch Flags & Environment Configuration
**Goal:** Prevent PyTorch/ComfyUI from using legacy FP16 operations on Pascal and select the optimal attention backend for `sm_60`.

### Implementation Steps
1. Open your launch script (`run_nvidia_gpu.bat` on Windows or `start.sh` on Linux).
2. Modify the startup command to include Pascal-optimized flags:
   ```bash
   python main.py \
     --force-fp32 \
     --fp16-vae \
     --use-pytorch-cross-attention \
     --highvram
   ```
3. Ensure PyTorch uses SDPA (Scaled Dot-Product Attention) instead of attempting to invoke FlashAttention (which requires `sm_70`+ Volta/Ampere).

### Verification & Testing
* **Test Case:** Run a standard SD1.5 or SDXL text-to-image workflow at $1024 \times 1024$ resolution with standard settings (e.g., 20 steps, Euler, Karras).
* **Metrics to Log:**
  * Total generation time / It/s (Iterations per second).
  * Check terminal outputs to ensure no `FlashAttention` warnings or silent fallbacks occur.

---

## Phase 2: Attention Kernel Upgrade (SageAttention)
**Goal:** Replace standard PyTorch attention with `SageAttention` to achieve quantized, fast cross-attention tailored for older CUDA compute capabilities.

### Implementation Steps
1. Install `SageAttention` into your ComfyUI Virtual Environment:
   ```bash
   pip install sageattention
   ```
2. Clone the custom node into your `custom_nodes` folder:
   ```bash
   cd ComfyUI/custom_nodes
   git clone https://github.com/kijai/ComfyUI-SageAttention
   ```
3. Insert the `SageAttention Integrator` or `Apply SageAttention` node into your workflow prior to model execution.

### Verification & Testing
* **Test Case:** Benchmark an SDXL or DiT (e.g., FLUX/Wan) generation before and after enabling SageAttention.
* **Metrics to Log:**
  * Verify `SageAttention` loads without CUDA kernel compilation errors on `sm_60`.
  * Observe speed improvements during the sampling phase (expect ~15–30% faster sampling step execution).

---

## Phase 3: Transitioning to GGUF Quantized Models
**Goal:** Leverage the P100’s massive 732 GB/s HBM2 bandwidth by loading GGUF-quantized UNet/DiT models, reducing VRAM usage and compute pressure.

### Implementation Steps
1. Install the `ComfyUI-GGUF` extension:
   ```bash
   cd ComfyUI/custom_nodes
   git clone https://github.com/city96/ComfyUI-GGUF
   ```
2. Download GGUF quantized models (`Q4_K_M` or `Q5_K_M`) for SDXL, FLUX, or Wan2.1 and place them in `ComfyUI/models/unet`.
3. In ComfyUI, replace the standard `Load Checkpoint` node with `Unet Loader (GGUF)` and wire it into the sampler.

### Verification & Testing
* **Test Case:** Run FLUX.1-dev or SDXL using a `Q4_K_M` GGUF vs. a standard FP16/FP32 model.
* **Metrics to Log:**
  * VRAM usage during model loading and generation (using `nvidia-smi`).
  * Time to First Iteration (Model load speed).

---

## Phase 4: Multi-P100 Scaling (Optional for Dual GPU Setup)
**Goal:** If a second Tesla P100 is added, implement data-parallel batch generation to scale throughput linearly.

### Implementation Steps
1. Install `ComfyUI-ParallelAnything` into `custom_nodes`:
   ```bash
   cd ComfyUI/custom_nodes
   git clone https://github.com/a16z-unofficial/ComfyUI-ParallelAnything
   ```
2. Configure GPU assignment in the node settings:
   * Set Device 0 (`cuda:0`) = 50% workload.
   * Set Device 1 (`cuda:1`) = 50% workload.
3. Enable P2P direct memory access if available on your motherboard/PCIe bridge.

### Verification & Testing
* **Test Case:** Run a batch generation of 4 images ($1024 \times 1024$).
* **Metrics to Log:**
  * Total time elapsed for 4 images on 1 GPU vs. 2 GPUs.
  * Check `nvidia-smi` to confirm both P100 GPUs reach near 100% compute utilization during sampling.

---

## Summary Testing Checklist

| Phase | Core Mechanism | Primary Goal | Target Metric |
| :--- | :--- | :--- | :--- |
| **Phase 1** | `--force-fp32` & SDPA | Avoid slow FP16 bottlenecks | Baseline It/s stability |
| **Phase 2** | SageAttention Node | Faster cross-attention math | +15–30% speedup in sampling |
| **Phase 3** | GGUF Quantization | Maximize HBM2 bandwidth usage | Low VRAM (~6-10GB), faster loading |
| **Phase 4** | Dual GPU Parallelism | Parallel batch rendering | ~1.8x total batch throughput |
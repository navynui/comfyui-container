# Agent Context & Environment Reference

This document is intended for AI coding agents working on the **llmaCPP** stack. This repository specifically manages the **ComfyUI** image generation backend.

## 🌐 Hybrid Development Setup

The development environment consists of two potential contexts:
1. **The Server Machine**:
   - Hosts the actual Docker container runtime and GPU hardware.
   - Files are located at `/home/nui/...` (e.g., `/home/nui/dev/comfyui-container`).
2. **The Dev Machine**:
   - Mounts the server's files remotely.
   - Paths on this machine map to `/home/nui/server/dev/comfyui-container`.

---

## 🧭 How to Orient Yourself

### Step 1: Detect your environment
Verify if `/home/nui/server` exists:
- If `/home/nui/server` is present, you are likely on the **Dev Machine**.
- If not, but `/home/nui/dev/comfyui-container` is present, you are on the **Server**.

### Step 2: Path translation

| Target Resource | Path on Server | Path on Dev Machine |
|:---|:---|:---|
| **Compose Directory** | `/home/nui/dev/comfyui-container` | `/home/nui/server/dev/comfyui-container` |
| **ComfyUI Source Code** | `/home/nui/dev/ComfyUI` | `/home/nui/server/dev/ComfyUI` |

### Step 3: Run commands on the correct host
- **Docker commands** must be run on the **Server** environment.
- If on the **Dev Machine**, do not run docker commands locally; they must be executed on the remote server host.

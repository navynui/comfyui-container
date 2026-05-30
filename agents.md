# Agent Context & Environment Reference

This document is intended for AI coding agents working on this project. It outlines the hybrid development environment and helps agents orient themselves to prevent incorrect path targeting or running commands on the wrong machine.

## 🌐 Hybrid Development Setup

The development environment consists of two potential contexts:
1. **The Server Machine**:
   - Hosts the actual Docker container runtime and GPU hardware.
   - Files are located at `/home/nui/...` (e.g., `/home/nui/dev/comfyui-container`).
2. **The Dev Machine**:
   - Mounts the server's files remotely under `/home/nui/server/...`.
   - Paths on this machine map to `/home/nui/server/dev/comfyui-container` and `/home/nui/server/dev/ComfyUI`.

---

## 🧭 How to Orient Yourself

As an agent, you may be running either on the **Server** itself or on the **Dev Machine**. Always perform a quick sanity check before executing shell commands or editing files.

### Step 1: Detect your environment
Verify if `/home/nui/server` exists:
- If `/home/nui/server` is present and contains folders like `dev`, you are likely running on the **Dev Machine**.
- If `/home/nui/server` does not exist, but `/home/nui/dev/comfyui-container` is present directly, you are likely running on the **Server**.

### Step 2: Path translation
Depending on where you are running, adjust your working directories and file edit targets accordingly:

| Target Resource | Path on Server | Path on Dev Machine |
|:---|:---|:---|
| **Compose Directory** | `/home/nui/dev/comfyui-container` | `/home/nui/server/dev/comfyui-container` |
| **ComfyUI Source Code** | `/home/nui/dev/ComfyUI` | `/home/nui/server/dev/ComfyUI` |

### Step 3: Run commands on the correct host
- **Docker commands** (`docker compose up`, `docker compose down`, etc.) must be run on the **Server** environment.
- If you are running on the **Dev Machine**, do not attempt to run docker commands locally unless you SSH into the server, or the terminal tools you are using are pre-configured to execute commands on the remote server host. Check your current command execution capabilities.

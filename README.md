# ComfyUI Docker Deployment & Maintenance Guide

This repository contains the configuration and maintenance scripts for running **ComfyUI** in a GPU-accelerated Docker container.

## 🖥️ Network & Directory Architecture

This deployment operates across two machines:
1. **Server (`192.168.1.129` or similar `.129` IP)**: Runs the Docker daemon, GPU resource container, and hosts the physical files.
2. **Dev Machine (`192.168.1.159` or similar `.159` IP)**: Mounts the server's filesystem under `/home/nui/server` for remote development and configuration.

### Directory Mapping
| Dev Machine (`.159` IP) | Server (`.129` IP) | Container Internals | Purpose |
|:---|:---|:---|:---|
| `/home/nui/server/dev/comfyui-container` | `/home/nui/dev/comfyui-container` | `/workspace` (or execution context) | Docker Compose and script definitions |
| `/home/nui/server/dev/ComfyUI` | `/home/nui/dev/ComfyUI` | `/opt/ComfyUI` | Core ComfyUI source code |
| `/home/nui/server/dev/ComfyUI/custom_nodes` | `/home/nui/dev/ComfyUI/custom_nodes` | `/opt/ComfyUI/custom_nodes` | Custom node extensions (git-tracked repos) |
| `/home/nui/server/dev/ComfyUI/models` | `/home/nui/dev/ComfyUI/models` | `/opt/ComfyUI/models` | AI Model checkpoints, VAEs, LoRAs, etc. |
| `/home/nui/server/dev/ComfyUI/output` | `/home/nui/dev/ComfyUI/output` | `/opt/ComfyUI/output` | Generated outputs and images |
| `/home/nui/server/dev/ComfyUI/user` | `/home/nui/dev/ComfyUI/user` | `/opt/ComfyUI/user` | User settings, ComfyUI-Manager config, profiles |

---

## 🚀 Running the Container

All docker-compose commands must be executed **on the Server (`.129`)** in the `/home/nui/dev/comfyui-container` directory.

### Start the ComfyUI Service
```bash
docker compose up -d
```

### Stop the ComfyUI Service
```bash
docker compose down
```

### View Real-time Logs
```bash
docker compose logs -f comfyui
```

### Accessing the Web UI
Open your browser and navigate to:
* **Direct IP**: `http://<server-ip>:8188` (e.g., `http://192.168.1.129:8188`)

---

## 🛠️ Maintenance & Update Scripts

Three scripts are provided to manage updates and automatic provisioning:

### 1. `update.sh` (Core & Stack Updates)
Use this script to update ComfyUI Core, ComfyUI-Manager, rebuild the container, and update dependencies.
* **Usage (on Server)**:
  ```bash
  ./update.sh
  ```
* **What it does**:
  1. Stashes local edits, pulls the latest `master` branch for core **ComfyUI**.
  2. Pulls the latest code for **ComfyUI-Manager**.
  3. Rebuilds and restarts the container stack (`docker compose down && docker compose up -d --force-recreate`).
  4. Runs `pip install -r requirements.txt` inside the container's virtualenv to sync Python packages.
  5. Automatically follows the container logs.

### 2. `update_nodes.sh` (Custom Nodes Mass Update)
Use this script to quickly update all installed Custom Nodes that are tracked via Git.
* **Usage (on Server)**:
  ```bash
  ./update_nodes.sh
  ```
* **What it does**:
  1. Iterates over all directories inside `/home/nui/dev/ComfyUI/custom_nodes`.
  2. Runs `git pull` on each Git repository found.
  3. Recycles the ComfyUI process inside the container using `supervisorctl` without needing to restart the Docker container itself.

### 3. `provisioning.sh` (Automatic Container Pre-seeding)
This script is run automatically by the `ai-dock` container entrypoint during startup.
* **What it does**:
  1. Upgrades pip and pre-installs system packages (`toml`, `gguf`, `sqlalchemy`, `alembic`, `blake3`) required by various models/nodes.
  2. Creates a proxy/wrapper for `pip` inside the virtualenv so that ComfyUI-Manager can install python dependencies successfully.
  3. Pre-seeds or adjusts `ComfyUI-Manager/config.ini` to set `security_level = normal` so package installations aren't blocked.

---

## 📦 Docker Details & GPU Settings

* **Docker Image**: `ghcr.io/ai-dock/comfyui:latest-cuda`
* **Virtual Environment Path inside Container**: `/opt/environments/python/comfyui`
* **GPU Configuration**:
  The stack utilizes the NVIDIA Container Toolkit to access host GPUs. Under the `deploy` section:
  * Driver capabilities: `[gpu, compute, utility, video]`
  * Host IPC: `host` and Shared Memory (`shm_size`) is set to `16gb` to allow efficient PyTorch tensor sharing.

# ComfyUI — Image Generation Component

This repository manages the **ComfyUI** Docker container, which serves as the image generation engine for the **llmaCPP** control center.

## 🏗️ Role in the Stack

ComfyUI provides the backend for high-quality image and batch generation. It is integrated into the `llmaCPP` stack and is primarily controlled via the **`llm-manager`** web interface.

- **Control Layer**: `llm-manager` (Port `8000`) sends API requests to ComfyUI.
- **Execution Layer**: `comfyui-container` (Port `8188`) processes the generation tasks.
- **Storage**: Generated images are stored in `/home/nui/dev/ComfyUI/output`, which is mapped to the `llm-manager` for gallery display.

## 🖥️ Directory Architecture

| Path | Container Internals | Purpose |
|:---|:---|:---|
| `/home/nui/dev/comfyui-container` | `/workspace` | Docker Compose and maintenance scripts |
| `/home/nui/dev/ComfyUI` | `/opt/ComfyUI` | Core ComfyUI source code |
| `/home/nui/dev/ComfyUI/custom_nodes` | `/opt/ComfyUI/custom_nodes` | Custom node extensions |
| `/home/nui/dev/ComfyUI/models` | `/opt/ComfyUI/models` | AI Model checkpoints, VAEs, LoRAs |
| `/home/nui/dev/ComfyUI/output` | `/opt/ComfyUI/output` | Generated outputs (accessed by `llm-manager`) |

---

## 🚀 Operations

### Container Control
Commands should be run from `/home/nui/dev/comfyui-container`:
- **Start**: `docker compose up -d`
- **Stop**: `docker compose down`
- **Logs**: `docker compose logs -f comfyui`

### Maintenance Scripts
Three specialized scripts are provided for system upkeep:

1. **`update.sh`**: Updates ComfyUI Core and Manager, rebuilds the container, and syncs Python dependencies.
2. **`update_nodes.sh`**: Mass updates all git-tracked custom nodes and recycles the process.
3. **`provisioning.sh`**: Automatic pre-seeding of system packages and ComfyUI-Manager config during container startup.

---

## 📦 Technical Details

- **Image**: `ghcr.io/ai-dock/comfyui:latest-cuda`
- **GPU**: Utilizes NVIDIA Container Toolkit with `shm_size: 16gb` for efficient tensor sharing.
- **Integration**: Exposed via `host.docker.internal:8188` to the `llm-manager` service.

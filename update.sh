#!/bin/bash
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

# ============================================================
#  PINNED for Tesla P100 (sm_60 / Pascal). This environment is
#  INTENTIONALLY FROZEN. This script RESTORES the known-good
#  state; it can never upgrade away from it.
#
#  Why these pins (do NOT change them):
#  - ComfyUI core 68806143: the LAST commit before b481bc15
#    ('Support gqa on all attention backends, drop support for
#    pytorch 2.4'). That rewrite changed Boogu's attention; on the
#    P100 there is no flash-attn backend, so the new path falls back
#    to the math backend, materializes the full 720x1280 attention
#    matrix and OOMs at 16 GB. The pre-rewrite attention is the
#    frugal one that fits. 68806143 still has krea2/boogu CLIP
#    types and pins comfy-kitchen 0.2.16 (pre-list[int]).
#  - torch 2.4.1+cu121: the runtime the old Boogu attention was
#    validated against; still ships sm_60 kernels. torch >= 2.7
#    DROPPED sm_60, so any newer torch kills generation on the P100.
#
#  This script does NOT: pull latest ComfyUI master, pull a newer
#  docker image, upgrade torch, or touch custom nodes.
# ============================================================
PINNED_COMMIT="68806143"
TORCH_VER="2.4.1"
TORCH_VISION="0.19.1"
TORCH_AUDIO="2.4.1"
CUDA_INDEX="https://download.pytorch.org/whl/cu121"

echo -e "${BLUE}=== ComfyUI Maintenance (PINNED / P100-safe - restores known-good state) ===${NC}"

# 1. Force ComfyUI core to the pinned commit. Never pulls latest master.
if [ -d "../ComfyUI/.git" ]; then
    echo -e "${YELLOW}[1/3] Pinning ComfyUI Core to ${PINNED_COMMIT}...${NC}"
    cd ../ComfyUI
    git fetch --all >/dev/null 2>&1
    git checkout -q "$PINNED_COMMIT"
    cd ../comfyui-container
fi

# 2. Rebuild/restart the container. No 'docker compose pull' -> the image
#    (and its bundled venv) is never changed; our venv volume persists.
echo -e "${YELLOW}[2/3] Restarting ComfyUI container (venv volume preserved)...${NC}"
docker compose down
docker compose up -d --force-recreate

# 3. Re-assert the P100-safe Python stack inside the venv. These explicit
#    pins WIN over anything, so the state cannot drift to a broken torch.
#    We intentionally do NOT run 'pip install -r requirements.txt' (it has an
#    unpinned 'torch' that would pull 2.7+ and drop sm_60 support).
echo -e "${YELLOW}[3/3] Re-asserting torch ${TORCH_VER}+cu121 (sm_60) + comfy-kitchen 0.2.16...${NC}"
sleep 3
docker compose exec comfyui /opt/environments/python/comfyui/bin/pip install \
  torch=="$TORCH_VER" torchvision=="$TORCH_VISION" torchaudio=="$TORCH_AUDIO" \
  --index-url "$CUDA_INDEX" 2>&1 | tail -2
docker compose exec comfyui /opt/environments/python/comfyui/bin/pip uninstall -y xformers 2>/dev/null || true
docker compose exec comfyui /opt/environments/python/comfyui/bin/pip install --no-deps comfy-kitchen==0.2.16 2>&1 | tail -1

echo -e "${GREEN}=== Done. ComfyUI is at the frozen P100-safe state (68806143 / torch 2.4.1). ===${NC}"
docker compose logs -f comfyui

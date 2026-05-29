#!/bin/bash
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
NC='\033[0m'

echo -e "${BLUE}=== Starting ComfyUI & Manager Maintenance Update ===${NC}"

# 1. Update Core ComfyUI Repository Code Tree
if [ -d "../ComfyUI/.git" ]; then
    echo -e "${YELLOW}[1/3] Updating ComfyUI Core Source Code...${NC}"
    cd ../ComfyUI
    git stash -u
    git fetch --all
    git checkout master
    git reset --hard origin/master
    git pull origin master
    git stash pop 2>/dev/null || git clean -fd
    cd ../comfyui-container
fi

# 2. Update ComfyUI-Manager Code Tree
if [ -d "../ComfyUI/custom_nodes/ComfyUI-Manager/.git" ]; then
    echo -e "${YELLOW}[2/3] Updating ComfyUI-Manager Extension Code...${NC}"
    cd ../ComfyUI/custom_nodes/ComfyUI-Manager
    git stash -u
    git fetch --all
    git checkout main 2>/dev/null || git checkout master
    git pull origin $(git branch --show-current)
    git stash pop 2>/dev/null || git clean -fd
    cd ../../../comfyui-container
fi

# 3. Rebuild and restart the container engine
echo -e "${YELLOW}[3/3] Rebuilding Docker Stack Containers...${NC}"
docker compose down
docker compose up -d --force-recreate

# 4. CRITICAL: Force-sync Python dependencies into the persistent venv volume
echo -e "${YELLOW}[4/4] Syncing Python Package Dependencies inside Container...${NC}"
sleep 3
docker compose exec comfyui /opt/environments/python/comfyui/bin/python -m pip install -r /opt/ComfyUI/requirements.txt

echo -e "${GREEN}=== System Successfully Updated and Restarted! ===${NC}"
docker compose logs -f comfyui

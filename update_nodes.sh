#!/bin/env bash

# Exit on error for non-iterative commands
set -e

# --- Configuration ---
NODES_DIR="$HOME/dev/ComfyUI/custom_nodes"
COMPOSE_DIR="$HOME/dev/comfyui-container"

# Colors for scannable terminal output
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Fixed literal color bleed reset
BOLD='\033[1m'

echo -e "${BOLD}${YELLOW}=== Starting ComfyUI Custom Nodes Mass Update ===${NC}\n"

if [ ! -d "$NODES_DIR" ]; then
    echo -e "${RED}[ERROR] Custom nodes directory not found at: $NODES_DIR${NC}"
    exit 1
fi

# Move to the target custom nodes workspace
cd "$NODES_DIR"

# Loop through all items inside the custom_nodes layout
for dir in *; do
    # Verify it is a directory and contains a .git metadata path
    if [ -d "$dir" ] && [ -d "$dir/.git" ]; then
        echo -e "${BOLD}Updating node:${NC} ${YELLOW}$dir${NC}"

        # Move into the node repository context
        cd "$dir"

        # Attempt to pull changes natively
        if git pull; then
            echo -e "${GREEN}[SUCCESS] Updated $dir cleanly.${NC}\n"
        else
            echo -e "${RED}[WARNING] Failed to pull changes for $dir. Skipping...${NC}\n"
        fi

        # Step back up to root custom_nodes context
        cd "$NODES_DIR"
    elif [ -d "$dir" ] && [ "$dir" != "__pycache__" ]; then
        echo -e "${YELLOW}[INFO] Skipping '$dir' (Not a tracked Git repository).${NC}\n"
    fi
done

# --- Cycle the ComfyUI Stack Process ---
echo -e "${BOLD}${YELLOW}=== Restarting ComfyUI Container Service ===${NC}"

if [ -d "$COMPOSE_DIR" ]; then
    cd "$COMPOSE_DIR"
    if docker compose ps | grep -q "comfyui"; then
        # CRITICAL FIX: Running supervisorctl as root inside the container
        docker compose exec -u root comfyui supervisorctl restart comfyui
        echo -e "\n${GREEN}[SUCCESS] ComfyUI stack process cycled flawlessly!${NC}"
    else
        echo -e "\n${RED}[ERROR] comfyui container is not actively running. Run 'docker compose up -d' first.${NC}"
    fi
else
    echo -e "\n${RED}[ERROR] Docker compose directory not found at $COMPOSE_DIR${NC}"
    exit 1
fi

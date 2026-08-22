#!/bin/env bash

# FROZEN for Tesla P100 (sm_60). Custom nodes are pinned at commits compatible
# with ComfyUI core 68806143 + torch 2.4.1. Pulling LATEST nodes can require a
# newer core / torch>=2.5 and silently break generation on the P100.
#
# By default this script does NOTHING (it will not break the working state).
# To override and pull latest nodes anyway (may break P100 generation), run:
#     FORCE_UPDATE_NODES=1 ./update_nodes.sh

set -e

NODES_DIR="$HOME/dev/ComfyUI/custom_nodes"
COMPOSE_DIR="$HOME/dev/comfyui-container"

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'
BOLD='\033[1m'

echo -e "${BOLD}${YELLOW}=== ComfyUI Custom Nodes Update (FROZEN / P100-safe) ===${NC}"

if [ "${FORCE_UPDATE_NODES:-0}" != "1" ]; then
    echo -e "${YELLOW}Custom nodes are FROZEN at pinned commits for P100 compatibility.${NC}"
    echo -e "${YELLOW}No changes made. To update nodes anyway (may break generation), run:${NC}"
    echo -e "   ${BOLD}FORCE_UPDATE_NODES=1 $0${NC}"
    exit 0
fi

echo -e "${RED}[WARNING] FORCE_UPDATE_NODES=1: pulling LATEST custom nodes.${NC}"
echo -e "${RED}This may require torch>=2.5 / a newer ComfyUI core and break the P100.${NC}"

if [ ! -d "$NODES_DIR" ]; then
    echo -e "${RED}[ERROR] Custom nodes directory not found at: $NODES_DIR${NC}"
    exit 1
fi

cd "$NODES_DIR"

for dir in *; do
    if [ -d "$dir" ] && [ -d "$dir/.git" ]; then
        echo -e "${BOLD}Updating node:${NC} ${YELLOW}$dir${NC}"
        cd "$dir"
        if git pull; then
            echo -e "${GREEN}[SUCCESS] Updated $dir cleanly.${NC}\n"
        else
            echo -e "${RED}[WARNING] Failed to pull changes for $dir. Skipping...${NC}\n"
        fi
        cd "$NODES_DIR"
    elif [ -d "$dir" ] && [ "$dir" != "__pycache__" ]; then
        echo -e "${YELLOW}[INFO] Skipping '$dir' (Not a tracked Git repository).${NC}\n"
    fi
done

echo -e "${BOLD}${YELLOW}=== Restarting ComfyUI Container Service ===${NC}"
if [ -d "$COMPOSE_DIR" ]; then
    cd "$COMPOSE_DIR"
    if docker compose ps | grep -q "comfyui"; then
        docker compose exec -u root comfyui supervisorctl restart comfyui
        echo -e "\n${GREEN}[SUCCESS] ComfyUI stack process cycled.${NC}"
    else
        echo -e "\n${RED}[ERROR] comfyui container is not running. Run 'docker compose up -d' first.${NC}"
    fi
fi

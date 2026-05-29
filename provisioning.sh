#!/bin/bash

VENV_PYTHON="/opt/environments/python/comfyui/bin/python"
CONFIG_INI="/opt/ComfyUI/user/default/ComfyUI-Manager/config.ini"

if [ -f "$VENV_PYTHON" ]; then
    echo "=== [Syncing Venv Packages] ==="
    $VENV_PYTHON -m pip install --upgrade pip
    
    # Force installation of core system tools along with your options
    $VENV_PYTHON -m pip install toml gguf sqlalchemy alembic blake3

    if [ ! -f "/opt/environments/python/comfyui/bin/pip3" ]; then
        echo "=== [Generating Pip Executable Proxy for ComfyUI-Manager] ==="
        echo '#!/bin/bash' > /opt/environments/python/comfyui/bin/pip
        echo '/opt/environments/python/comfyui/bin/python -m pip "$@"' >> /opt/environments/python/comfyui/bin/pip
        chmod +x /opt/environments/python/comfyui/bin/pip
    fi
fi

if [ -f "$CONFIG_INI" ]; then
    echo "=== [Lowering Security Level to Normal] ==="
    sed -i 's/security_level = .*/security_level = normal/g' "$CONFIG_INI"
else
    echo "=== [Pre-seeding ComfyUI-Manager config.ini] ==="
    mkdir -p "$(dirname "$CONFIG_INI")"
    echo -e "[ComfyUI-Manager]\nsecurity_level = normal" > "$CONFIG_INI"
fi

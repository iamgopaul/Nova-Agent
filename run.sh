#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

kill_port_listener() {
	local port="$1"
	local pids
	pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
	if [[ -z "$pids" ]]; then
		return
	fi

	echo "Clearing port $port (PID: $pids)"
	kill $pids 2>/dev/null || true

	# Wait briefly for graceful shutdown, then force-kill if still bound.
	local attempt
	for attempt in 1 2 3 4 5; do
		if ! lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1; then
			return
		fi
		sleep 0.2
	done

	pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
	if [[ -n "$pids" ]]; then
		echo "Force clearing port $port (PID: $pids)"
		kill -9 $pids 2>/dev/null || true
	fi
}

# Clear stale dev listeners that commonly block startup.
kill_port_listener 8765
kill_port_listener 3000
kill_port_listener 3001
kill_port_listener 3002

# ── Python venv — create and install if missing ───────────────────────────────
if [[ ! -f "$ROOT_DIR/.venv/bin/activate" ]]; then
    echo "[Nova] Creating Python virtual environment..."
    python3 -m venv "$ROOT_DIR/.venv"
fi

source "$ROOT_DIR/.venv/bin/activate"

# Install/update Python dependencies if pyproject.toml changed since last install.
STAMP="$ROOT_DIR/.venv/.nova_install_stamp"
PYPROJECT="$ROOT_DIR/pyproject.toml"
if [[ ! -f "$STAMP" || "$PYPROJECT" -nt "$STAMP" ]]; then
    echo "[Nova] Installing Python dependencies..."
    pip install --quiet --upgrade pip
    pip install --quiet -e "$ROOT_DIR"
    touch "$STAMP"
    echo "[Nova] Python dependencies ready."
fi

# ── Bun — install frontend deps if node_modules missing or stale ─────────────
PKGJSON="$ROOT_DIR/frontend/package.json"
NODE_MODULES="$ROOT_DIR/frontend/node_modules"
BUN_LOCK="$ROOT_DIR/frontend/bun.lockb"
NODE_STAMP="$ROOT_DIR/frontend/node_modules/.nova_install_stamp"

if ! command -v bun &>/dev/null; then
    echo "[Nova] Bun not found — installing..."
    curl -fsSL https://bun.sh/install | bash
    export PATH="$HOME/.bun/bin:$PATH"
fi

if [[ ! -d "$NODE_MODULES" || ! -f "$NODE_STAMP" || "$PKGJSON" -nt "$NODE_STAMP" || ( -f "$BUN_LOCK" && "$BUN_LOCK" -nt "$NODE_STAMP" ) ]]; then
    echo "[Nova] Installing frontend dependencies..."
    bun install --cwd "$ROOT_DIR/frontend" --frozen-lockfile 2>/dev/null \
        || bun install --cwd "$ROOT_DIR/frontend"
    touch "$NODE_STAMP"
    echo "[Nova] Frontend dependencies ready."
fi

# ── Detect available RAM and set Ollama limits accordingly ────────────────────
AVAIL_RAM_GB=$(python3 -c "import psutil; print(int(psutil.virtual_memory().available / 1024**3))" 2>/dev/null || echo "8")
TOTAL_RAM_GB=$(python3 -c "import psutil; print(int(psutil.virtual_memory().total / 1024**3))" 2>/dev/null || echo "16")
echo "[Nova] Memory: ${AVAIL_RAM_GB} GB available / ${TOTAL_RAM_GB} GB total"

if   [ "$AVAIL_RAM_GB" -lt 3 ]; then
    RAM_TIER="critical"
    MAX_MODELS=1
    NUM_PARALLEL=1
elif [ "$AVAIL_RAM_GB" -lt 7 ]; then
    RAM_TIER="moderate"
    MAX_MODELS=2
    NUM_PARALLEL=1
else
    RAM_TIER="ok"
    MAX_MODELS=3
    NUM_PARALLEL=2
fi
echo "[Nova] RAM tier: $RAM_TIER"

# ── Ollama performance tuning ─────────────────────────────────────────────────
# Allow parallel inference (useful when routing + main call overlap)
export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-$NUM_PARALLEL}"
# Keep models hot in memory between requests — eliminates reload delays
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-$MAX_MODELS}"
# Enable flash attention — ~20–30% speed boost on supported models (Ollama ≥ 0.3)
export OLLAMA_FLASH_ATTENTION="${OLLAMA_FLASH_ATTENTION:-1}"
# Reduce reserved GPU overhead so more VRAM goes to model layers
export OLLAMA_GPU_OVERHEAD="${OLLAMA_GPU_OVERHEAD:-0}"
# Allow memory-mapped model loading so the OS can page weights under RAM pressure
export OLLAMA_NOPRUNE="${OLLAMA_NOPRUNE:-0}"

echo "[Nova] Ollama: parallel=$OLLAMA_NUM_PARALLEL  max_models=$OLLAMA_MAX_LOADED_MODELS  flash_attn=$OLLAMA_FLASH_ATTENTION  ram_tier=$RAM_TIER"

# Prefetch MediaPipe hand_landmarker.task (~8 MB) so the first camera frame is instant.
echo "[Nova] Prefetching vision models..."
python "$ROOT_DIR/scripts/ensure_models.py" || echo "[Nova] Warning: model prefetch failed — will retry when the camera runs."

python "$ROOT_DIR/scripts/run_local_app.py"
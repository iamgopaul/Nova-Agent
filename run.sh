#!/usr/bin/env bash
# GAAIA — cross-platform launcher (macOS, Linux, Windows/Git Bash)
# Auto-installs Python 3.12+, pnpm, and project dependencies on first run.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

# ── OS detection ──────────────────────────────────────────────────────────────
case "$(uname -s)" in
	MINGW*|MSYS*|CYGWIN*) OS="windows" ;;
	Darwin)               OS="mac" ;;
	Linux)                OS="linux" ;;
	*)                    OS="unknown" ;;
esac

if [[ "$OS" == "windows" ]]; then
	VENV_PY=".venv/Scripts/python.exe"
else
	VENV_PY=".venv/bin/python"
fi

log() { printf "[GAAIA] %s\n" "$*"; }
err() { printf "[GAAIA] ERROR: %s\n" "$*" >&2; }

# ── Cross-platform port killer ────────────────────────────────────────────────
kill_port_listener() {
	local port="$1"
	if [[ "$OS" == "windows" ]]; then
		local pids
		pids="$(netstat -ano -p tcp 2>/dev/null \
			| awk -v p=":$port" '$2 ~ p"$" && $4=="LISTENING" {print $5}' \
			| sort -u)"
		[[ -z "$pids" ]] && return
		log "Clearing port $port (PID: $pids)"
		for pid in $pids; do
			taskkill //PID "$pid" //F >/dev/null 2>&1 || true
		done
		return
	fi

	command -v lsof >/dev/null 2>&1 || return
	local pids
	pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
	[[ -z "$pids" ]] && return
	log "Clearing port $port (PID: $pids)"
	kill $pids 2>/dev/null || true
	for _ in 1 2 3 4 5; do
		lsof -nP -iTCP:"$port" -sTCP:LISTEN >/dev/null 2>&1 || return
		sleep 0.2
	done
	pids="$(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null || true)"
	if [[ -n "$pids" ]]; then
		log "Force clearing port $port (PID: $pids)"
		kill -9 $pids 2>/dev/null || true
	fi
}

for port in 8765 3000 3001 3002; do
	kill_port_listener "$port"
done

# ── Find Python 3.12+ (install if missing) ────────────────────────────────────
python_version() {
	# Prints "MAJ MIN" for the given command, or nothing if it can't run.
	# shellcheck disable=SC2086
	$1 -c 'import sys; print(sys.version_info[0], sys.version_info[1])' 2>/dev/null || true
}

is_py312_plus() {
	local out maj min
	out="$(python_version "$1")"
	[[ -z "$out" ]] && return 1
	maj="${out%% *}"; min="${out##* }"
	(( maj > 3 || (maj == 3 && min >= 12) ))
}

find_python() {
	local candidates
	if [[ "$OS" == "windows" ]]; then
		# NOTE: paths must not contain spaces — python_version() relies on word-splitting
		# so it can also accept multi-word commands like "py -3.12".
		candidates=(
			"py -3.13" "py -3.12"
			"python3.13" "python3.12" "python3" "python"
			"$HOME/AppData/Local/Programs/Python/Python313/python.exe"
			"$HOME/AppData/Local/Programs/Python/Python312/python.exe"
		)
	else
		candidates=("python3.13" "python3.12" "python3" "python")
	fi
	for c in "${candidates[@]}"; do
		if is_py312_plus "$c"; then
			echo "$c"
			return 0
		fi
	done
	return 1
}

install_python() {
	log "Python 3.12+ not found — installing..."
	case "$OS" in
		windows)
			command -v winget >/dev/null 2>&1 || {
				err "winget unavailable. Install Python 3.12 manually: https://www.python.org/downloads/"; exit 1; }
			# winget returns non-zero when the package is already installed; tolerate it.
			winget install --id Python.Python.3.12 --silent \
				--accept-package-agreements --accept-source-agreements --scope user || true
			# Make the new interpreter visible to this shell.
			local py_root="$HOME/AppData/Local/Programs/Python/Python312"
			[[ -d "$py_root" ]] && export PATH="$py_root:$py_root/Scripts:$PATH"
			;;
		mac)
			command -v brew >/dev/null 2>&1 || {
				err "Homebrew not installed. Install from https://brew.sh, then re-run."; exit 1; }
			brew install python@3.12
			# Homebrew Python on Apple Silicon lives under /opt/homebrew, Intel under /usr/local.
			for prefix in /opt/homebrew /usr/local; do
				[[ -x "$prefix/opt/python@3.12/bin/python3.12" ]] && export PATH="$prefix/opt/python@3.12/bin:$PATH"
			done
			;;
		linux)
			if command -v apt-get >/dev/null 2>&1; then
				# python3.12 is not in default Ubuntu < 24.04 repos — fall back to deadsnakes PPA.
				if ! apt-cache show python3.12 >/dev/null 2>&1; then
					log "Adding deadsnakes PPA (python3.12 not in default repos)..."
					sudo apt-get update
					sudo apt-get install -y software-properties-common
					sudo add-apt-repository -y ppa:deadsnakes/ppa
					sudo apt-get update
				fi
				sudo apt-get install -y python3.12 python3.12-venv python3.12-dev
			elif command -v dnf >/dev/null 2>&1; then
				sudo dnf install -y python3.12
			elif command -v pacman >/dev/null 2>&1; then
				sudo pacman -S --noconfirm python
			else
				err "Install Python 3.12+ via your package manager, then re-run."; exit 1
			fi
			;;
		*)
			err "Unknown OS. Install Python 3.12+ manually."; exit 1 ;;
	esac
}

PY_CMD="$(find_python || true)"
if [[ -z "$PY_CMD" ]]; then
	install_python
	PY_CMD="$(find_python || true)"
	if [[ -z "$PY_CMD" ]]; then
		err "Python 3.12+ install completed but interpreter not on PATH. Open a new terminal and re-run."
		exit 1
	fi
fi
log "Using Python: $PY_CMD ($($PY_CMD -c 'import sys; print(sys.version.split()[0])'))"

# ── Create / refresh venv ─────────────────────────────────────────────────────
needs_recreate=0
if [[ -f "$VENV_PY" ]]; then
	if ! is_py312_plus "$VENV_PY"; then
		log "Existing venv is older than Python 3.12 — recreating."
		needs_recreate=1
	fi
else
	needs_recreate=1
fi

if (( needs_recreate )); then
	rm -rf .venv
	log "Creating Python virtual environment..."
	# shellcheck disable=SC2086
	$PY_CMD -m venv .venv
fi

# ── Install Python deps if pyproject.toml changed since last install ──────────
STAMP=".venv/.gaaia_install_stamp"
if [[ ! -f "$STAMP" || "pyproject.toml" -nt "$STAMP" ]]; then
	log "Installing Python dependencies (this can take a few minutes on first run)..."
	"$VENV_PY" -m pip install --upgrade pip
	"$VENV_PY" -m pip install --progress-bar=on -e ".[imagegen,docgen,musicgen]"
	touch "$STAMP"
	log "Python dependencies ready."
fi

# ── Upgrade torch to a CUDA build if an NVIDIA GPU is present ────────────────
# pip ships the CPU build by default on Windows / Linux; if a CUDA GPU exists,
# swap once so SDXL image gen and any future torch-backed inference use the GPU.
# Apple Silicon already gets MPS via the default wheel — no swap needed.
ensure_cuda_torch() {
	[[ "$OS" == "mac" ]] && return 0
	command -v nvidia-smi >/dev/null 2>&1 || return 0
	nvidia-smi -L >/dev/null 2>&1 || return 0

	local cuda_ok
	cuda_ok="$("$VENV_PY" -c 'import torch; print("ok" if torch.cuda.is_available() else "no")' 2>/dev/null | tr -d '\r')"
	[[ "$cuda_ok" == "ok" ]] && return 0

	log "NVIDIA GPU detected but torch is CPU-only — swapping to CUDA build (~2.5 GB download)..."
	"$VENV_PY" -m pip install --upgrade --force-reinstall \
		torch torchvision torchaudio \
		--index-url https://download.pytorch.org/whl/cu124 \
		|| log "Warning: CUDA torch install failed — image gen will stay on CPU. (Try cu118 if your driver is old.)"
}
ensure_cuda_torch

# ── Frontend: pnpm (matches scripts/run_local_app.py) ─────────────────────────
ensure_pnpm() {
	command -v pnpm >/dev/null 2>&1 && return
	if command -v npm >/dev/null 2>&1; then
		log "pnpm not found — installing via npm..."
		npm install -g pnpm
		return
	fi
	err "Node.js not installed. Install Node 20+ from https://nodejs.org, then re-run."
	exit 1
}
ensure_pnpm

PKGJSON="frontend/package.json"
NODE_MODULES="frontend/node_modules"
NODE_STAMP="frontend/node_modules/.gaaia_install_stamp"
if [[ ! -d "$NODE_MODULES" || ! -f "$NODE_STAMP" || "$PKGJSON" -nt "$NODE_STAMP" ]]; then
	log "Installing frontend dependencies..."
	(cd frontend && pnpm install)
	touch "$NODE_STAMP"
	log "Frontend dependencies ready."
fi

# ── Unified memory tier (RAM + VRAM) for Ollama tuning ───────────────────────
# Probe RAM via psutil and VRAM via gaaia.services.hardware so the launcher's
# tier picker matches what the in-process model router will compute.
# tr -d '\r' strips CRLF that Python on Windows adds to stdout — without it,
# bash arithmetic later sees e.g. APPLE="0\r" and errors with "invalid arithmetic operator".
_probe_out="$("$VENV_PY" -c '
import psutil, sys
sys.path.insert(0, ".")
from gaaia.services.hardware import is_apple_silicon, nvidia_vram_gb, amd_vram_gb
m = psutil.virtual_memory()
apple = is_apple_silicon()
vram = 0.0 if apple else (nvidia_vram_gb() + amd_vram_gb())
print(int(m.available/1024**3), int(m.total/1024**3), int(vram), int(apple))
' 2>/dev/null | tr -d '\r')"
read -r AVAIL_RAM_GB TOTAL_RAM_GB VRAM_GB APPLE <<< "${_probe_out:-8 16 0 0}"

# Unified budget: on Apple Silicon, RAM == VRAM (unified memory); elsewhere, sum them.
if (( APPLE == 1 )); then
	BUDGET_GB="$AVAIL_RAM_GB"
	log "Memory: ${AVAIL_RAM_GB} GB available / ${TOTAL_RAM_GB} GB total (Apple Silicon unified)"
else
	BUDGET_GB=$(( AVAIL_RAM_GB + VRAM_GB ))
	if (( VRAM_GB > 0 )); then
		log "Memory: ${AVAIL_RAM_GB} GB RAM available + ${VRAM_GB} GB VRAM = ${BUDGET_GB} GB budget"
	else
		log "Memory: ${AVAIL_RAM_GB} GB RAM available (no GPU detected)"
	fi
fi

if   (( BUDGET_GB < 3 )); then  RAM_TIER="critical"; MAX_MODELS=1; NUM_PARALLEL=1
elif (( BUDGET_GB < 7 )); then  RAM_TIER="moderate"; MAX_MODELS=2; NUM_PARALLEL=1
elif (( BUDGET_GB < 24 )); then RAM_TIER="ok";       MAX_MODELS=3; NUM_PARALLEL=2
else                            RAM_TIER="generous"; MAX_MODELS=4; NUM_PARALLEL=4
fi
log "Memory tier: $RAM_TIER"

# Silence the harmless HuggingFace warning about Windows lacking symlinks (Kokoro cache).
export HF_HUB_DISABLE_SYMLINKS_WARNING="${HF_HUB_DISABLE_SYMLINKS_WARNING:-1}"

export OLLAMA_NUM_PARALLEL="${OLLAMA_NUM_PARALLEL:-$NUM_PARALLEL}"
export OLLAMA_MAX_LOADED_MODELS="${OLLAMA_MAX_LOADED_MODELS:-$MAX_MODELS}"
export OLLAMA_FLASH_ATTENTION="${OLLAMA_FLASH_ATTENTION:-1}"
# KV-cache quantization halves the per-token KV memory at near-zero quality
# cost (q8_0). Critical for tight-VRAM systems running long contexts: a 28K
# context on a 12B model drops from ~5 GB to ~2.5 GB of KV cache, which can
# be the difference between fitting on an 8 GB GPU and spilling to RAM.
# Requires OLLAMA_FLASH_ATTENTION=1 (set above). Override with q4_0 for an
# extra 50 % memory cut at modest quality cost, or f16 to disable.
export OLLAMA_KV_CACHE_TYPE="${OLLAMA_KV_CACHE_TYPE:-q8_0}"
export OLLAMA_GPU_OVERHEAD="${OLLAMA_GPU_OVERHEAD:-0}"
export OLLAMA_NOPRUNE="${OLLAMA_NOPRUNE:-0}"
log "Ollama: parallel=$OLLAMA_NUM_PARALLEL  max_models=$OLLAMA_MAX_LOADED_MODELS  flash_attn=$OLLAMA_FLASH_ATTENTION  kv_cache=$OLLAMA_KV_CACHE_TYPE  memory_tier=$RAM_TIER"

# ── Ollama: install, start, and pull a starter model if none exist ────────────
ensure_ollama() {
	# Make the Windows user-scope install discoverable in this shell.
	if [[ "$OS" == "windows" ]]; then
		local win_dir="$HOME/AppData/Local/Programs/Ollama"
		[[ -d "$win_dir" ]] && export PATH="$win_dir:$PATH"
	fi

	if ! command -v ollama >/dev/null 2>&1; then
		log "Ollama not found — installing..."
		case "$OS" in
			windows)
				command -v winget >/dev/null 2>&1 || {
					err "winget unavailable. Install Ollama from https://ollama.com/download"; return 1; }
				winget install --id Ollama.Ollama --silent \
					--accept-package-agreements --accept-source-agreements --scope user || true
				local win_dir="$HOME/AppData/Local/Programs/Ollama"
				[[ -d "$win_dir" ]] && export PATH="$win_dir:$PATH"
				;;
			mac)
				command -v brew >/dev/null 2>&1 \
					&& brew install ollama \
					|| { err "Install Ollama from https://ollama.com/download"; return 1; }
				;;
			linux)
				curl -fsSL https://ollama.com/install.sh | sh
				;;
		esac
	fi
	command -v ollama >/dev/null 2>&1 || {
		err "Ollama installed but not on PATH. Open a new terminal and re-run."; return 1; }

	# Start Ollama if the API isn't already responding.
	if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
		log "Starting Ollama service..."
		# Detach so it survives this shell.
		(nohup ollama serve >/dev/null 2>&1 &) >/dev/null 2>&1 || true
		for _ in 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15; do
			curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break
			sleep 1
		done
	fi
	if ! curl -sf http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
		log "Warning: Ollama did not come up on 127.0.0.1:11434 — chat may not work."
		return 0
	fi

	# Pull only the models that fit this host's memory budget. The router auto-promotes
	# to bigger models if they later become available — so upgrading RAM/GPU and re-running
	# this script will pull the additional models without any other config changes.
	# Override with GAAIA_PULL_ALL=1 to pull every model regardless of fit (archival).
	local stamp=".venv/.gaaia_models_stamp"
	local mode_flag=""
	local mode_label="adaptive — only models that fit this host"
	if [[ "${GAAIA_PULL_ALL:-0}" == "1" ]]; then
		mode_flag="--no-ram-filter"
		mode_label="all models (GAAIA_PULL_ALL=1) — includes models too big for this host"
	fi

	# Compute desired set. Stamp stores this list so re-runs re-pull when either the
	# hardware budget grows OR _ROLE_FALLBACKS changes.
	# tr -d '\r' is required on Windows where Python emits CRLF line endings.
	local desired
	# shellcheck disable=SC2086
	desired="$("$VENV_PY" scripts/list_pullable_models.py $mode_flag 2>/dev/null | tr -d '\r')"

	if [[ -f "$stamp" ]] && [[ "$desired" == "$(cat "$stamp" 2>/dev/null)" ]]; then
		log "Models up to date with host budget (mode: $mode_label)."
	else
		log "Pulling models — mode: $mode_label"
		local pull_failures=0
		while IFS= read -r model; do
			[[ -z "$model" ]] && continue
			log "  → ollama pull $model"
			ollama pull "$model" || { pull_failures=$((pull_failures + 1)); log "  ✗ failed: $model"; }
		done <<< "$desired"
		if (( pull_failures == 0 )); then
			printf '%s\n' "$desired" > "$stamp"
			log "All models pulled."
		else
			log "Done with $pull_failures failed pull(s); stamp not written so we'll retry next run."
		fi
	fi
}
ensure_ollama || true

# ── Prefetch MediaPipe asset so the first camera frame is instant ─────────────
log "Prefetching vision models..."
"$VENV_PY" scripts/ensure_models.py || log "Warning: model prefetch failed — will retry when the camera runs."

# ── Launch backend + frontend ─────────────────────────────────────────────────
"$VENV_PY" scripts/run_local_app.py

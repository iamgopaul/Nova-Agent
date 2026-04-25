#!/usr/bin/env bash
# GAAIA — First-time setup script
# Installs all free, local dependencies. Requires no paid services.
# Run once: bash scripts/setup.sh

set -e
GAAIA_DIR="$(cd "$(dirname "$0")/.." && pwd)"
cd "$GAAIA_DIR"

echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  GAAIA — Free Local Setup"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

# ── 1. Python virtual environment ─────────────────────────────────────
if [ ! -d ".venv" ]; then
    echo "→ Creating Python venv..."
    python3 -m venv .venv
fi
source .venv/bin/activate
echo "→ Installing Python dependencies..."
pip install -q --upgrade pip
pip install -q -e ".[dev]"
echo "  ✓ Python dependencies installed"

# ── 2. Ollama ─────────────────────────────────────────────────────────
echo ""
echo "→ Checking Ollama..."
if ! command -v ollama &>/dev/null; then
    echo "  Ollama not found. Installing via Homebrew..."
    if ! command -v brew &>/dev/null; then
        echo "  ERROR: Homebrew not installed."
        echo "  Install Homebrew first: https://brew.sh"
        echo "  Then re-run this script."
        exit 1
    fi
    brew install ollama
    echo "  ✓ Ollama installed"
else
    echo "  ✓ Ollama already installed: $(ollama --version)"
fi

# Start Ollama in background if not running
if ! curl -s http://localhost:11434 &>/dev/null; then
    echo "  Starting Ollama service..."
    ollama serve &>/dev/null &
    sleep 3
fi

# ── 3. Pull local models ───────────────────────────────────────────────
echo ""
echo "→ Pulling local models (this downloads model weights — one-time)..."
echo "  Primary model: qwen2.5:7b (~4.7 GB) — best tool-calling quality"
ollama pull qwen2.5:7b

echo ""
echo "  Fast model: llama3.2:3b (~2.0 GB) — low latency alternative"
ollama pull llama3.2:3b

echo "  ✓ Models ready"

# ── 4. .env file ──────────────────────────────────────────────────────
echo ""
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "  ✓ Created .env from .env.example"
    echo "  (No API keys needed — all services run locally)"
else
    echo "  ✓ .env already exists"
fi

# ── 5. Data directories ───────────────────────────────────────────────
mkdir -p ~/GAAIA/notes
echo "  ✓ Data directories ready at ~/GAAIA/"

# ── 6. Summary ────────────────────────────────────────────────────────
echo ""
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"
echo "  Setup complete. Everything runs locally. $0 cost."
echo ""
echo "  Test GAAIA:       .venv/bin/python scripts/test_day1.py"
echo "  Run desktop app: .venv/bin/python scripts/run_desktop.py"
echo ""
echo "  Stack summary:"
echo "  • LLM:    Ollama + qwen2.5:7b  (local, Metal GPU, free)"
echo "  • STT:    faster-whisper       (local, free)"
echo "  • TTS:    macOS say            (built-in, free)"
echo "  • Search: DuckDuckGo           (no key, free)"
echo "  • Memory: SQLite               (local, free)"
echo "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━"

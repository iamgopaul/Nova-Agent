# Nova — Personal AI Chief of Staff

Nova is a fully local, privacy-first AI assistant that runs on your own hardware via [Ollama](https://ollama.com). She combines a multi-model routing engine, live web research, computer vision, voice I/O, and real-time content generation into a single conversational interface — no cloud API keys required.

---

## What Nova Can Do

### Conversation & Research
- Answers questions, gives advice, and holds natural conversation with a distinct personality (Isabella — witty, warm, British-inflected)
- Routes each request to the best local model automatically (essay → 72B, code → coder, quick lookup → 3B, math → STEM specialist, etc.)
- Searches the web via DuckDuckGo and parses live RSS feeds (BBC, Reuters, AP, Hacker News) for current events and news
- Writes full essays, articles, and reports on any topic with proper headings, rich paragraphs, and sourced research
- Auto-fetches trending news every 5 minutes and injects it into context (live knowledge feed)

### Content Generation (all local)

| Type | Engine | Example trigger |
|------|--------|-----------------|
| Images | Stable Diffusion | "draw me a…", "generate an image of…" |
| Music / beats | MusicGen | "make a lo-fi beat", "compose a piano track" |
| Word / PDF / PPTX | python-docx / reportlab / python-pptx | "create a Word doc about…", "export as PDF" |
| Charts & graphs | matplotlib | "bar chart of…", "pie chart showing…" |
| Diagrams | Mermaid (frontend render) | "flowchart of…", "sequence diagram for…" |

### Voice
- Wake-word activation ("Hey Nova") or push-to-talk (`Ctrl+Space`)
- Speech-to-text via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) large-v3 (runs locally, great accent support)
- Text-to-speech via [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) (local, British female — Isabella) or ElevenLabs (optional)
- Per-speaker voice enrollment and identity recognition (ECAPA-TDNN embeddings)
- Barge-in / interrupt support

### Camera & Vision
- Live camera feed with continuous frame analysis
- Hand tracking (MediaPipe) — finger identity, gesture detection
- Object detection (YOLOv8n) — people count, labelled bounding boxes
- Face recognition (DeepFace / ArcFace) — enrolled user identity
- Scene description via vision LLM (llama3.2-vision)

### Developer Tools
- Read, list, and search local files and code repositories
- `git status` integration
- Screenshot capture and analysis

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Frontend (Next.js)                        │
│  Chat UI · Voice controls · Camera overlay · Generation UI  │
└────────────────────────┬────────────────────────────────────┘
                         │ HTTP / SSE  (localhost:8765)
┌────────────────────────▼────────────────────────────────────┐
│                    FastAPI Backend                           │
│  /chat  /voice  /image  /music  /document  /chart  /camera  │
└────────────────────────┬────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│                   Nova Agent Core                            │
│                                                              │
│  Orchestrator ──► Auto-Router ──► Model selector            │
│       │                                                      │
│       ├── Nova Pro     (qwen2.5:72b)        — essays, research      │
│       ├── Nova Core    (mistral:7b)         — everyday + tools      │
│       ├── Nova Spark   (llama3.2:3b)        — fast one-liners       │
│       ├── Nova Air     (gemma3:4b)          — light chat            │
│       ├── Nova Code    (qwen2.5-coder:32b)  — programming           │
│       ├── Nova Vision  (llama3.2-vision:11b)— image understanding   │
│       ├── Nova Quant   (mathstral:7b)       — maths & stats         │
│       └── Nova Reason  (deepseek-r1:7b)     — proofs & CoT          │
│                                                              │
│  Tool Registry — web search · weather · news · notes ·      │
│                  screenshot · clipboard · file ops · git     │
│                                                              │
│  Memory (SQLite) · Fact extraction · Context builder         │
└─────────────────────────────────────────────────────────────┘
                         │
┌────────────────────────▼────────────────────────────────────┐
│              Ollama  (localhost:11434)                       │
│          All models run 100% locally — no cloud             │
└─────────────────────────────────────────────────────────────┘
```

---

## Requirements

- **macOS** (Apple Silicon recommended — M-series Metal GPU acceleration)
- **Python 3.12+**
- **Node.js 20+** and **pnpm** (for the Next.js web UI)
- **[Ollama](https://ollama.com)** installed and running (`ollama serve`)
- **16 GB RAM minimum** (64 GB recommended for the 72B model at full quality)

---

## Quick Start

### 1. Install Ollama and pull models

```bash
# Install Ollama — https://ollama.com
brew install ollama
ollama serve   # keep this running in a terminal tab

# Core models (required)
ollama pull qwen2.5:72b           # Nova Pro — main reasoning model (~47 GB)
ollama pull mistral:7b            # Nova Core — everyday + tools (~4 GB)
ollama pull llama3.2:3b           # Nova Spark — ultra-fast (~2 GB)
ollama pull gemma3:4b             # Nova Air — light chat (~3 GB)
ollama pull qwen2.5-coder:32b    # Nova Code — programming (~20 GB)
ollama pull llama3.2-vision:11b   # Nova Vision — image understanding (~8 GB)

# Optional specialist models
ollama pull mathstral:7b          # Nova Quant — maths & statistics
ollama pull deepseek-r1:7b        # Nova Reason — proofs & chain-of-thought
```

> **Smaller setup:** Replace `qwen2.5:72b` with `qwen2.5:7b` in `config/config.yaml` to run on 8–16 GB RAM.

### 2. Set up the Python environment

```bash
cd "Nova Agent"
python3 -m venv .venv
source .venv/bin/activate

# Core install
pip install -e "."

# Install optional extras you want
pip install -e ".[docgen]"    # Word, Excel, PDF, PowerPoint generation
pip install -e ".[imagegen]"  # Stable Diffusion image generation
pip install -e ".[musicgen]"  # MusicGen beat / music generation
pip install -e ".[speakerid]" # ECAPA-TDNN speaker identity (SpeechBrain)
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env if needed — no API keys required for core features
```

### 4. Set up the frontend

```bash
cd frontend
pnpm install
cd ..
```

### 5. Run

**Web UI (recommended):**
```bash
./run-web.sh
# Opens at http://localhost:3000
```

**Desktop app (customtkinter):**
```bash
./run.sh
```

**Backend API only:**
```bash
source .venv/bin/activate
python scripts/run_server_only.py
# API docs at http://localhost:8765/docs
```

---

## API Reference (headless)

```bash
# Chat (streaming SSE)
curl -N -X POST http://localhost:8765/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "What is the weather in Miami?"}'

# Save a fact to memory
curl -X POST http://localhost:8765/memory/facts \
  -H "Content-Type: application/json" \
  -d '{"key": "user_name", "value": "Josh", "source": "user"}'

# Get stored facts
curl http://localhost:8765/memory/facts

# Interactive API docs
open http://localhost:8765/docs
```

---

## Configuration

All behavior is controlled by [`config/config.yaml`](config/config.yaml). Key sections:

| Section | What it controls |
|---------|-----------------|
| `model` | Ollama model names for each Nova persona, token budgets, temperatures |
| `personality` | Name, tone, response style, conciseness |
| `voice` | STT (faster-whisper), TTS (Kokoro / ElevenLabs / macOS say), wake words, audio thresholds |
| `camera` | YOLO model path, hand backend (MediaPipe / MMPose), face recognition |
| `memory` | SQLite DB path, conversation window sizes |
| `research` | Search provider, RSS news feeds |
| `knowledge_feed` | Auto-refresh interval and RSS sources for live context |
| `approval` | Which tools require user confirmation (auto / confirm / blocked) |

---

## Project Structure

```
Nova Agent/
├── config/
│   ├── config.yaml           # All settings — models, voice, camera, memory
│   └── settings.py           # Pydantic settings loader
├── nova/
│   ├── agent/
│   │   ├── orchestrator.py   # Core agentic loop, model routing, tool dispatch
│   │   ├── personality.py    # System prompt builder (Nova's character & rules)
│   │   └── tool_registry.py  # Tool registration & JSON schema generation
│   ├── engines/
│   │   ├── research.py       # Web search (DuckDuckGo) + news (RSS)
│   │   ├── media.py          # YouTube playback, music controls
│   │   ├── communication.py  # Email & message drafts
│   │   └── dev.py            # File ops, git status, code search
│   ├── memory/
│   │   ├── store.py          # SQLite conversation + fact storage
│   │   ├── context_builder.py# Injects memory & facts into LLM context
│   │   └── models.py         # SQLAlchemy ORM models
│   ├── server/
│   │   ├── main.py           # FastAPI app entrypoint & lifespan
│   │   └── routers/          # API routes: chat, voice, image, music, document…
│   ├── services/
│   │   ├── image_gen_service.py    # Stable Diffusion pipeline
│   │   ├── musicgen_service.py     # MusicGen pipeline
│   │   ├── document_gen_service.py # Word / Excel / PDF / PPTX generation
│   │   ├── chart_gen_service.py    # Chart rendering (matplotlib → PNG)
│   │   ├── camera_vision.py        # Vision LLM scene description
│   │   ├── frame_detection.py      # YOLO + MediaPipe frame processing
│   │   ├── face_identity.py        # DeepFace enrollment & recognition
│   │   └── speaker_identity.py     # Voice enrollment & recognition
│   ├── tools/                # Individual tool implementations
│   ├── voice/                # STT (Whisper) + TTS (Kokoro) pipelines
│   └── desktop/              # CustomTkinter desktop app
├── frontend/                 # Next.js web UI
│   └── app/
│       ├── page.tsx          # Main chat interface
│       └── api/              # Next.js API routes (proxy to backend)
├── scripts/
│   ├── run_desktop.py        # Desktop app launcher
│   ├── run_server_only.py    # Backend-only launcher
│   ├── ensure_models.py      # Pre-fetch MediaPipe / model assets
│   └── test_*.py             # Smoke tests (no Ollama needed for test_e2e.py)
├── data/                     # Runtime data — gitignored
├── tests/                    # Test suite
├── run.sh                    # Launch desktop app
├── run-web.sh                # Launch web UI (backend + frontend)
└── pyproject.toml            # Python package metadata + dependencies
```

---

## Smoke Tests

```bash
source .venv/bin/activate

# Full stack validation (no Ollama required)
python scripts/test_e2e.py

# With a live Ollama instance
python scripts/test_day1.py   # Basic conversation
python scripts/test_day2.py   # Tool loop (search, notes, screenshot)
python scripts/test_day3.py   # Memory & context
python scripts/test_day6.py   # Voice pipeline
```

---

## Privacy

- All LLM inference runs **100% locally** via Ollama — no data leaves your machine
- Web search uses DuckDuckGo (no account, no tracking)
- Speech-to-text and text-to-speech run entirely on-device (faster-whisper + Kokoro)
- Camera, face, and voice data never leave the local process
- The only optional cloud feature is ElevenLabs TTS (disabled by default; Kokoro is the default)

---

## Built With

- [Ollama](https://ollama.com) — local LLM runtime
- [FastAPI](https://fastapi.tiangolo.com) — backend API
- [Next.js](https://nextjs.org) — web frontend
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — speech-to-text
- [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) — text-to-speech
- [MediaPipe](https://mediapipe.dev) — hand tracking
- [Ultralytics YOLOv8](https://docs.ultralytics.com) — object detection
- [DeepFace](https://github.com/serengil/deepface) — face recognition
- [DuckDuckGo Search](https://github.com/deedy5/duckduckgo_search) — web search
- [Diffusers](https://huggingface.co/docs/diffusers) — Stable Diffusion image generation
- [MusicGen](https://huggingface.co/facebook/musicgen-small) — music generation

---

## License

MIT © Josh Gopaul

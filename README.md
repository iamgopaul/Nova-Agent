# GAAIA — Personal AI Chief of Staff

GAAIA is a fully local, privacy-first AI platform that runs entirely on your own hardware via [Ollama](https://ollama.com). It combines a multi-model routing engine, live web research, computer vision, voice I/O, real-time content generation, multi-model debate, and an education suite — all in a single conversational interface with no cloud API keys required.

---

## Feature Overview

### Conversation & Research
- Natural conversation with a distinct personality (Isabella — witty, warm, British-inflected)
- **Auto model routing** — every request is scored and sent to the best-fit local model (essay → 72B, code → coder, math → STEM specialist, quick reply → 3B, etc.)
- **RAM-aware model selection** at startup — the model router queries Ollama, measures available RAM, and automatically substitutes smaller fallbacks when a configured model won't fit
- Web search via DuckDuckGo (Brave Search when an API key is provided) with live result parsing
- Live RSS news feeds (BBC, Reuters, AP, Hacker News) — current events injected automatically
- Full essays, articles, and reports with sourced research and proper structure
- **Knowledge Feed** — background scheduler fetches trending content every hour and injects it into context

### Content Generation (all local)

| Type | Engine | Example triggers |
|------|--------|-----------------|
| Images | Stable Diffusion (Diffusers) | "draw me a…", "generate an image of…" |
| Music / beats | MusicGen | "make a lo-fi beat", "compose a piano track" |
| Word / PDF / PPTX / XLSX | python-docx / reportlab / python-pptx / openpyxl | "create a Word doc about…", "export as PDF" |
| Charts & graphs | matplotlib | "bar chart of…", "pie chart showing…" |
| Diagrams | Mermaid (frontend render) | "flowchart of…", "sequence diagram for…" |

### Voice
- Wake-word activation ("Hey GAAIA") or push-to-talk (`Ctrl+Space`)
- Speech-to-text via [faster-whisper](https://github.com/SYSTRAN/faster-whisper) large-v3 — runs locally, strong accent support
- Text-to-speech via [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) (local, British female — Isabella) or ElevenLabs (optional cloud)
- **Per-speaker voice enrollment and identity recognition** (ECAPA-TDNN embeddings via SpeechBrain)
- **Voice personalization** — per-user TTS voice preferences and STT prompt optimization
- Barge-in / interrupt support; speaker focus (directs GAAIA to the primary speaker)
- Video frame context injection into voice responses

### Camera & Vision
- Live camera feed with continuous frame analysis
- **Hand tracking** (MediaPipe Hands Tasks) — finger identity, count, gesture detection
- **Pose estimation** (MediaPipe Pose Tasks) — full-body landmark tracking
- **Object detection** (YOLOv8n) — people count, labelled bounding boxes, false-positive suppression on hands/skin
- **Face recognition** (DeepFace / ArcFace) — enrolled user identity with per-frame identification
- **Scene description** via vision LLM (llama3.2-vision) — natural language scene understanding
- Detection geometry pipeline — NMS, IOU, hand-region suppression, finger deduplication
- Optional MMPose RTMPose backend for hands

### GAAIA Debate
- Enter any question or topic and watch two AI models argue opposing positions live
- **Proponent** (light/fast model) vs **Opposition** (medium/core model) across three rounds: Opening → Rebuttal → Closing
- Tokens stream in real time to each model's identity card as they "speak"
- **MiroFish-style arena** — animated entity orbs with pulsing rings, speaking bars, and thinking indicators
- **Moderator** synthesizes the debate, scores both sides (1–10), declares a winner, and produces the best combined answer
- Full scrollable debate transcript with chat-bubble layout

### Education
- **Quiz & exam generator** — produce multiple-choice, short-answer, or essay questions on any topic
- Difficulty levels: elementary → middle → high → college → bachelor's → master's → doctorate
- Upload a document (PDF) and generate questions grounded in its content
- **Auto-grading** — submit answers and receive per-question feedback with a final score
- Smart model selection — routes to technical specialists for STEM topics, reasoning models for complex analysis

### Authentication & Users
- Local user accounts (email + bcrypt password)
- **OAuth 2.0** — Google and GitHub sign-in
- JWT session tokens (HTTP-only cookie)
- Per-user memory, voice profiles, and debate history

### Web Watcher
- User-defined watch topics with background hourly refresh
- Summarized results stored in the database and surfaced in context
- Enable/disable individual topics; run a manual refresh on demand

### System Monitoring
- Live stats bar in the UI — CPU%, RAM, GPU VRAM, model inference time
- **Resource Advisor** — adaptive Ollama inference parameter tuning based on RAM pressure (`ok` / `moderate` / `critical`): adjusts `num_ctx`, `num_batch`, `num_thread`, `use_mmap`, `mlock`, `num_gpu`
- Per-request performance metrics (TTFT, tokens/sec, total duration)
- `/stats/models` endpoint — shows which models were auto-selected and why

---

## Model Fleet

GAAIA routes across 18 specialized personas. All are Ollama models — swap any for whatever you have installed; the model router will find the best available substitute.

| Persona | Default model | Best for |
|---------|--------------|---------|
| GAAIA Pro | qwen2.5:72b | Deep research, long essays, complex reasoning |
| GAAIA Core | mistral:7b | Everyday conversation, tool use, balanced tasks |
| GAAIA Spark | llama3.2:3b | Ultra-fast replies, voice one-liners |
| GAAIA Air | gemma3:4b | Light conversational chat |
| GAAIA Code | qwen2.5-coder:32b | Programming, code review, debugging |
| GAAIA Vision | llama3.2-vision:11b | Image and scene understanding |
| GAAIA Mind | gemma3:27b | Deep nuanced discussion, no tool calls |
| GAAIA Creative | dolphin-mixtral:8x7b | Writing, brainstorming, ideation |
| GAAIA Insight | zephyr:7b | Analysis, structured reasoning |
| GAAIA Sage | nous-hermes:13b | Instruction following, document Q&A |
| GAAIA Chat | neural-chat:7b | Friendly, casual conversation |
| GAAIA Logic | orca-mini:7b | Concise logical tasks |
| GAAIA Mini | phi:2.7b | Smallest, snappiest model |
| GAAIA Star | starling-lm:7b | Polished general responses |
| GAAIA Open | openchat:7b | Baseline open-source responses |
| GAAIA Quant | mathstral:7b | Maths, statistics, numerical reasoning |
| GAAIA Reason | deepseek-r1:70b | Chain-of-thought, proofs, multi-step logic |
| GAAIA Heavy | qwen2.5:72b | Alias for Pro — explicit heavy-task routing |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                         Frontend  (Next.js 15)                        │
│                                                                       │
│  /chat      /voice    /debate   /education  /home                    │
│  /image     /music    /ide      /podcast    /agents                  │
│  /auth      settings  stats-bar camera-overlay                       │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │  HTTP / SSE   (localhost:8765)
┌───────────────────────────────▼──────────────────────────────────────┐
│                         FastAPI Backend                               │
│                                                                       │
│  /chat     /voice    /debate   /education  /image   /music           │
│  /document /chart    /camera   /memory     /stats   /watcher         │
│  /auth     /auth/oauth                                                │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │
┌───────────────────────────────▼──────────────────────────────────────┐
│                          GAAIA Agent Core                              │
│                                                                       │
│  Orchestrator ──► Auto-Router ──► Model Router (RAM-aware)           │
│       │                                                               │
│       ├── GAAIA Pro      (qwen2.5:72b)         — essays, research     │
│       ├── GAAIA Core     (mistral:7b)           — everyday + tools    │
│       ├── GAAIA Spark    (llama3.2:3b)          — fast one-liners     │
│       ├── GAAIA Air      (gemma3:4b)            — light chat          │
│       ├── GAAIA Code     (qwen2.5-coder:32b)    — programming         │
│       ├── GAAIA Vision   (llama3.2-vision:11b)  — image & scene       │
│       ├── GAAIA Mind     (gemma3:27b)           — deep reasoning      │
│       ├── GAAIA Creative (dolphin-mixtral:8x7b) — writing             │
│       ├── GAAIA Quant    (mathstral:7b)         — maths & stats       │
│       └── GAAIA Reason   (deepseek-r1:70b)      — chain-of-thought    │
│                                                                       │
│  Tool Registry — web search · weather · news · notes · file ops      │
│                  screenshot · clipboard · git · media · email         │
│                                                                       │
│  Memory (SQLite) · Fact extraction · Context builder                 │
│  Knowledge Feed · Web Watcher · Resource Advisor                     │
│  Speaker Identity · Voice Personalization                             │
│  Frame Detection · Face Identity · Camera Buffer                     │
└───────────────────────────────┬──────────────────────────────────────┘
                                 │
┌───────────────────────────────▼──────────────────────────────────────┐
│                    Ollama  (localhost:11434)                          │
│              All inference runs 100% locally — no cloud              │
└──────────────────────────────────────────────────────────────────────┘
```

---

## Requirements

| Requirement | Version |
|-------------|---------|
| macOS (Apple Silicon recommended) | Sonoma 14+ |
| Python | 3.12+ |
| Node.js | 20+ |
| pnpm | 9+ |
| [Ollama](https://ollama.com) | latest |
| RAM | 16 GB minimum · 64 GB for 72B model |

> Linux is supported. Windows is untested.

---

## Quick Start

### 1. Install Ollama and pull models

```bash
brew install ollama
ollama serve   # keep running in a terminal tab

# Minimum set (runs on 16 GB RAM)
ollama pull mistral:7b            # GAAIA Core — everyday + tools (~4 GB)
ollama pull llama3.2:3b           # GAAIA Spark — ultra-fast (~2 GB)
ollama pull gemma3:4b             # GAAIA Air — light chat (~3 GB)
ollama pull llama3.2-vision:11b   # GAAIA Vision — image understanding (~8 GB)

# Recommended additions
ollama pull qwen2.5:32b           # GAAIA Pro on 32 GB machines (~22 GB)
ollama pull qwen2.5-coder:32b     # GAAIA Code — programming (~20 GB)
ollama pull deepseek-r1:7b        # GAAIA Reason — chain-of-thought (~5 GB)
ollama pull mathstral:7b          # GAAIA Quant — maths & stats (~5 GB)

# Full setup (64 GB+ recommended)
ollama pull qwen2.5:72b           # GAAIA Pro — flagship (~47 GB)
```

> The model router automatically falls back to the best installed model for each role, so you don't need to pull everything — just pull what fits your RAM.

### 2. Set up the Python environment

```bash
cd "GAAIA Agent"
python3 -m venv .venv
source .venv/bin/activate

# Core install
pip install -e "."

# Optional extras
pip install -e ".[docgen]"    # Word, Excel, PDF, PowerPoint generation
pip install -e ".[imagegen]"  # Stable Diffusion image generation
pip install -e ".[musicgen]"  # MusicGen beat / music generation
pip install -e ".[speakerid]" # ECAPA-TDNN speaker identity (SpeechBrain)
pip install -e ".[mmpose]"    # MMPose RTMPose hand backend (advanced)
```

### 3. Configure

```bash
cp .env.example .env
# Edit .env — all fields are optional; GAAIA works with zero API keys
```

Key optional `.env` variables:

```env
BRAVE_SEARCH_API_KEY=    # Brave Search (free tier: 2k/month) — uses DuckDuckGo if blank
ELEVENLABS_API_KEY=      # ElevenLabs TTS — uses local Kokoro if blank
GOOGLE_CLIENT_ID=        # Google OAuth sign-in
GOOGLE_CLIENT_SECRET=
GITHUB_CLIENT_ID=        # GitHub OAuth sign-in
GITHUB_CLIENT_SECRET=
```

### 4. Set up the frontend

```bash
cd frontend
pnpm install
cd ..
```

### 5. Run

```bash
./run.sh
# Opens at http://localhost:3000
# API docs at http://localhost:8765/docs
```

**Backend only (no frontend):**
```bash
source .venv/bin/activate
python scripts/run_server_only.py
```

---

## Pages

| Page | Path | Description |
|------|------|-------------|
| Chat | `/chat` | Main conversational interface with streaming, images, web results, documents |
| Voice | `/voice` | Push-to-talk and wake-word voice conversation with camera context |
| Debate | `/debate` | Multi-model live debate arena — two AIs argue, moderator synthesizes |
| Education | `/education` | Quiz & exam generator with PDF context and auto-grading |
| Home | `/home` | Hub dashboard linking all modules |
| IDE | `/ide` | Code-focused chat with file and repo awareness |
| Podcast | `/podcast` | Long-form audio content generation |
| Agents | `/agents` | Agent configuration and management |
| Settings | `/settings` | Model, voice, camera, and feature toggles |

---

## API Reference

All endpoints require a `gaaia_token` cookie (obtained via `/auth/login` or `/auth/register`).

```bash
# Register / login
curl -X POST http://localhost:8765/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email":"you@example.com","password":"secret","display_name":"Josh"}'

# Chat (streaming SSE)
curl -N -X POST http://localhost:8765/chat \
  -H "Content-Type: application/json" \
  -H "Cookie: gaaia_token=<token>" \
  -d '{"message":"What is the weather in Miami?"}'

# Start a debate
curl -X POST http://localhost:8765/debate/start \
  -H "Content-Type: application/json" \
  -H "Cookie: gaaia_token=<token>" \
  -d '{"topic":"Should AI be regulated by governments?"}'
# Returns: {"debate_id":"...", "proponent":{...}, "opposition":{...}, "moderator":{...}}

# Stream the debate
curl -N http://localhost:8765/debate/<debate_id>/stream \
  -H "Cookie: gaaia_token=<token>"

# Generate a quiz
curl -X POST http://localhost:8765/education/generate \
  -H "Content-Type: application/json" \
  -H "Cookie: gaaia_token=<token>" \
  -d '{"topic":"Quantum computing","difficulty":"college","num_questions":5}'

# Save a fact to memory
curl -X POST http://localhost:8765/memory/facts \
  -H "Content-Type: application/json" \
  -H "Cookie: gaaia_token=<token>" \
  -d '{"key":"user_name","value":"Josh","source":"user"}'

# System stats
curl http://localhost:8765/stats

# Model routing info
curl http://localhost:8765/stats/models

# Interactive API docs
open http://localhost:8765/docs
```

---

## Configuration

All behavior is controlled by [`config/config.yaml`](config/config.yaml).

| Section | Controls |
|---------|---------|
| `model` | Ollama model names for each GAAIA persona, token budgets, temperatures, context lengths |
| `personality` | Name, tone, response style, conciseness target |
| `voice` | STT engine (faster-whisper), TTS engine (Kokoro / ElevenLabs / macOS say), wake words, audio thresholds |
| `camera` | YOLO model path, hand backend (MediaPipe / MMPose), face recognition config |
| `memory` | SQLite DB path, conversation window sizes, fact retention |
| `research` | Search provider, RSS news feeds, article snippet count |
| `knowledge_feed` | Auto-refresh interval, RSS sources for live background context |
| `approval` | Which tools require user confirmation (`auto` / `confirm` / `blocked`) |
| `app` | Data directory, port, frontend URL |

---

## Project Structure

```
GAAIA Agent/
├── config/
│   ├── config.yaml                  # All settings — models, voice, camera, memory
│   └── settings.py                  # Pydantic settings loader + model router integration
│
├── gaaia/
│   ├── agent/
│   │   ├── orchestrator.py          # Core agentic loop, model routing, tool dispatch, streaming
│   │   ├── personality.py           # System prompt builder (GAAIA's character & rules)
│   │   └── tool_registry.py         # Tool registration & JSON schema generation
│   │
│   ├── engines/
│   │   ├── research.py              # Web search (DuckDuckGo / Brave) + RSS news
│   │   ├── media.py                 # YouTube playback, music controls
│   │   ├── communication.py         # Email & message drafts
│   │   ├── dev.py                   # File ops, git status, code search
│   │   └── video_analyzer.py        # Video frame analysis pipeline
│   │
│   ├── memory/
│   │   ├── store.py                 # SQLite conversation + fact storage
│   │   ├── context_builder.py       # Injects memory & facts into LLM context
│   │   └── models.py                # SQLAlchemy ORM models (User, Message, Fact, …)
│   │
│   ├── server/
│   │   ├── main.py                  # FastAPI app entrypoint & lifespan hooks
│   │   ├── dependencies.py          # Shared FastAPI dependencies (auth, memory, orchestrator)
│   │   ├── schemas.py               # Shared Pydantic request/response schemas
│   │   ├── security.py              # Security headers middleware
│   │   └── routers/
│   │       ├── auth.py              # Local register / login / logout / profile
│   │       ├── oauth.py             # Google & GitHub OAuth 2.0
│   │       ├── chat.py              # Streaming chat (SSE), image gen, document gen
│   │       ├── debate.py            # Multi-model debate arena (SSE)
│   │       ├── education.py         # Quiz generation, grading, document context
│   │       ├── voice.py             # STT, TTS, wake-word, speaker identity
│   │       ├── camera.py            # Live frame detection, face enrollment, scene description
│   │       ├── image.py             # Stable Diffusion image generation
│   │       ├── music.py             # MusicGen beat / music generation
│   │       ├── document.py          # Word / PDF / PPTX / XLSX document generation
│   │       ├── chart.py             # Chart generation (matplotlib → PNG)
│   │       ├── memory.py            # Facts, conversation history, voice sessions
│   │       ├── stats.py             # System resources + inference metrics
│   │       └── watcher.py           # Web Watcher topic CRUD + manual refresh
│   │
│   ├── services/
│   │   ├── model_router.py          # RAM-aware model selection (18 personas, fallback chains)
│   │   ├── resource_advisor.py      # Adaptive Ollama inference tuning (num_ctx, num_batch, …)
│   │   ├── image_generator.py       # Stable Diffusion pipeline
│   │   ├── music_generator.py       # MusicGen pipeline
│   │   ├── document_generator.py    # Word / Excel / PDF / PPTX generation
│   │   ├── chart_generator.py       # Chart rendering (matplotlib → PNG)
│   │   ├── camera_vision.py         # Vision LLM scene description
│   │   ├── frame_detection.py       # YOLO + MediaPipe unified detection (pre-fused model fix)
│   │   ├── body_detector.py         # MediaPipe Hands / Face / Pose Tasks
│   │   ├── hand_tracker.py          # MediaPipe hand landmark detection
│   │   ├── mmpose_tracker.py        # MMPose RTMPose hand backend
│   │   ├── detection_geometry.py    # NMS, IOU, hand-region suppression helpers
│   │   ├── detection_stabilizer.py  # Temporal detection smoothing
│   │   ├── face_identity.py         # DeepFace enrollment & recognition (thread-safe import)
│   │   ├── speaker_identity.py      # Voice enrollment & ECAPA-TDNN recognition
│   │   ├── voice_personalization.py # Per-user TTS voice prefs & STT prompt tuning
│   │   ├── camera_buffer.py         # Live camera frame buffer
│   │   ├── camera_context.py        # Camera context line formatter for LLM prompts
│   │   ├── video_camera.py          # JPEG frame extraction from video bytes
│   │   ├── knowledge_feed.py        # Background RSS / news feed scheduler
│   │   ├── web_watcher.py           # User-defined topic watch scheduler
│   │   ├── stats_tracker.py         # Per-request inference metrics
│   │   ├── response_cache.py        # Response deduplication cache
│   │   ├── prompt_enhancer.py       # Image prompt enhancement via LLM
│   │   ├── image_decode.py          # JPEG / PNG → OpenCV BGR helper
│   │   ├── location.py              # IP-based location lookup
│   │   ├── mediapipe_runtime.py     # MediaPipe Tasks runtime wrapper
│   │   └── mediapipe_resources.py   # MediaPipe model asset manager
│   │
│   ├── voice/
│   │   ├── stt.py                   # faster-whisper STT pipeline
│   │   ├── tts.py                   # Kokoro / ElevenLabs / macOS say TTS pipeline
│   │   ├── pipeline.py              # Full voice conversation pipeline
│   │   ├── audio_io.py              # Microphone capture & audio playback
│   │   ├── hotkey.py                # Ctrl+Space push-to-talk handler
│   │   └── speaker_focus.py         # Speaker focus / primary-speaker detection
│   │
│   └── tools/                       # Individual tool implementations (search, notes, …)
│
├── frontend/                         # Next.js 15 web UI
│   ├── app/
│   │   ├── page.tsx                  # Root redirect
│   │   ├── home/page.tsx             # Hub dashboard
│   │   ├── chat/page.tsx             # Main chat interface
│   │   ├── voice/page.tsx            # Voice conversation UI
│   │   ├── debate/page.tsx           # Debate arena UI
│   │   ├── education/page.tsx        # Education / quiz UI
│   │   ├── ide/page.tsx              # Code-focused chat
│   │   ├── podcast/page.tsx          # Podcast generation
│   │   ├── agents/page.tsx           # Agent management
│   │   ├── auth/                     # Login / register / OAuth callback pages
│   │   └── api/                      # Next.js route handlers (proxy to FastAPI)
│   │       ├── chat/                 # Chat SSE proxy
│   │       ├── debate/               # Debate start + SSE proxy
│   │       ├── education/            # Quiz / grade proxies
│   │       ├── voice/                # Voice STT / TTS proxy
│   │       ├── camera/               # Camera detection proxy
│   │       ├── image/                # Image generation proxy
│   │       ├── music/                # Music generation proxy
│   │       ├── document/             # Document generation proxy
│   │       ├── chart/                # Chart proxy
│   │       ├── memory/               # Memory proxy
│   │       ├── stats/                # Stats proxy
│   │       └── watcher/              # Web Watcher proxy
│   ├── components/
│   │   ├── app-shell.tsx             # Consistent page frame (header, stats bar, footer)
│   │   ├── app-footer.tsx            # Navigation footer
│   │   └── chat/                     # Chat-specific components
│   ├── lib/
│   │   ├── gaaia-api-base.ts          # Backend base URL helper
│   │   ├── chat-messages-persist.ts  # Chat history persistence
│   │   └── utils.ts                  # Tailwind cn() and shared utilities
│   └── hooks/                        # Custom React hooks
│
├── scripts/
│   ├── run_local_app.py              # Backend + frontend process manager
│   ├── run_server_only.py            # Backend-only launcher
│   ├── ensure_models.py              # Pre-fetch MediaPipe / model assets
│   ├── setup.sh                      # One-time dependency setup helper
│   ├── test_conversation.py          # Smoke test: basic conversation
│   ├── test_tools.py                 # Smoke test: tool loop (search, notes, screenshot)
│   ├── test_memory.py                # Smoke test: memory & context
│   ├── test_voice.py                 # Smoke test: voice pipeline
│   └── test_e2e.py                   # Full stack validation (no Ollama required)
│
├── data/                             # Runtime data — gitignored
│   ├── gaaia.db                       # SQLite database (users, memory, facts, topics)
│   └── GAAIA/                         # User data (face DB, voice profiles, generated files)
│
├── run.sh                            # Launch GAAIA (kills old ports, starts backend + frontend)
├── pyproject.toml                    # Python package metadata + optional extras
└── .env.example                      # Environment variable template
```

---

## Smoke Tests

```bash
source .venv/bin/activate

# No Ollama required — validates server startup, auth, and routing
python scripts/test_e2e.py

# Requires a running Ollama instance
python scripts/test_conversation.py   # Basic conversation
python scripts/test_tools.py          # Tool loop (search, notes, screenshot)
python scripts/test_memory.py         # Memory & context injection
python scripts/test_voice.py          # Voice pipeline (STT + TTS)
```

---

## Privacy

- All LLM inference runs **100% locally** via Ollama — no prompts, responses, or user data leave your machine
- Web search uses DuckDuckGo by default (no account, no tracking); Brave Search is an optional opt-in
- Speech-to-text (faster-whisper) and text-to-speech (Kokoro) run entirely on-device
- Camera feed, face data, and voice profiles never leave the local process
- OAuth tokens are stored locally in SQLite; no third-party analytics
- The only optional cloud features are ElevenLabs TTS and Brave Search (both disabled by default)

---

## Built With

- [Ollama](https://ollama.com) — local LLM runtime
- [FastAPI](https://fastapi.tiangolo.com) — backend API & SSE streaming
- [Next.js 15](https://nextjs.org) — web frontend (App Router, Tailwind CSS v4)
- [faster-whisper](https://github.com/SYSTRAN/faster-whisper) — speech-to-text
- [Kokoro](https://huggingface.co/hexgrad/Kokoro-82M) — local text-to-speech
- [MediaPipe](https://mediapipe.dev) — hand tracking, face detection, pose estimation
- [Ultralytics YOLOv8](https://docs.ultralytics.com) — object detection
- [DeepFace](https://github.com/serengil/deepface) — face recognition (ArcFace)
- [SpeechBrain](https://speechbrain.github.io) — speaker identity (ECAPA-TDNN)
- [DuckDuckGo Search](https://github.com/deedy5/duckduckgo_search) — web search
- [Diffusers](https://huggingface.co/docs/diffusers) — Stable Diffusion image generation
- [MusicGen](https://huggingface.co/facebook/musicgen-small) — music generation
- [SQLAlchemy](https://www.sqlalchemy.org) + SQLite — persistent memory
- [shadcn/ui](https://ui.shadcn.com) + Tailwind CSS — UI components

---

## License

MIT © Josh Gopaul

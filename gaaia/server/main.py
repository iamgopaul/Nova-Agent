from __future__ import annotations

import warnings
from contextlib import asynccontextmanager

# ── Suppress noisy third-party deprecation warnings ───────────────────────────
# These come from torch internals (weight_norm, jit.script), mediapipe Swig
# bindings, HuggingFace Hub auth hints, and Kokoro LSTM dropout.
# None of them affect GAAIA's behaviour — they are upstream library issues.
warnings.filterwarnings("ignore", category=FutureWarning, module="torch")
warnings.filterwarnings("ignore", category=DeprecationWarning, module="torch")
warnings.filterwarnings("ignore", category=UserWarning, module="torch")
warnings.filterwarnings("ignore", message=".*builtin type Swig.*")
warnings.filterwarnings("ignore", message=".*dropout option adds dropout.*")
warnings.filterwarnings("ignore", message=".*repo_id.*Kokoro.*")
warnings.filterwarnings("ignore", message=".*unauthenticated requests to the HF Hub.*")
warnings.filterwarnings("ignore", message=".*HF_TOKEN.*")
warnings.filterwarnings("ignore", message=".*duckduckgo_search.*renamed.*ddgs.*")

import os
os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
# Silence HuggingFace Hub auth warning entirely
os.environ.setdefault("HF_HUB_VERBOSITY", "error")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from gaaia.server.security import SecurityHeadersMiddleware

from config.settings import get_settings
from gaaia.bootstrap import build_nova
from gaaia.server.routers import agents, auth, camera, chart, chat, debate, document, education, image, memory, music, oauth, podcast, screen, stats, video, voice, watcher
from gaaia.services.knowledge_feed import KnowledgeFeedScheduler
from gaaia.services.web_watcher import WatcherScheduler
from gaaia.services.location import get_location, location_context
from gaaia.services import resource_advisor


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Probe hardware once and start background refresh thread
    resource_advisor.initialize()

    settings = get_settings()

    # ── Model routing — pick best models that fit in system RAM ──────────────
    from gaaia.services.model_router import run_model_routing
    _ollama_host = str(settings._yaml.get("model", {}).get("host") or "http://localhost:11434")
    _mr_overrides, _mr_ram_gb, _mr_installed, _mr_logs = run_model_routing(
        settings._yaml.get("model", {}),
        host=_ollama_host,
    )
    settings.apply_model_routing(_mr_overrides)
    print(
        f"[ModelRouter] System RAM: {_mr_ram_gb:.1f} GB | "
        f"Installed models: {len(_mr_installed)} | "
        f"Role overrides: {len(_mr_overrides)}",
        flush=True,
    )
    for line in _mr_logs:
        print(f"[ModelRouter]{line}", flush=True)
    # Store routing info for the /stats/models endpoint
    app.state.model_routing = {
        "ram_gb": round(_mr_ram_gb, 1),
        "installed_models": sorted(_mr_installed),
        "overrides": _mr_overrides,
        "log": _mr_logs,
    }

    mem, orchestrator, approval = build_nova(settings)

    app.state.settings    = settings
    app.state.memory      = mem
    app.state.orchestrator = orchestrator
    app.state.approval    = approval

    from gaaia.services.face_identity import FaceIdentityStore
    from pathlib import Path
    cam_cfg = settings.camera
    face_cfg = cam_cfg.get("face_recognition", {})
    app.state.face_identity = FaceIdentityStore(
        db_path=Path(face_cfg.get("db_path", "~/GAIA/face_db")).expanduser(),
        model_name=face_cfg.get("model", "ArcFace"),
        distance_metric=face_cfg.get("distance_metric", "cosine"),
        threshold=float(face_cfg.get("threshold", 0.40)),
        enabled=bool(cam_cfg.get("enabled", True)),
        detector_backend=face_cfg.get("detector_backend", "opencv"),
    )

    loc = await get_location()
    loc_ctx = location_context(loc)
    app.state.location_context = loc_ctx
    orchestrator._location_ctx = loc_ctx
    if loc:
        print(f"[GAIA] Location: {loc.get('city')}, {loc.get('regionName')}, {loc.get('country')}", flush=True)
    else:
        print("[GAIA] Location unavailable — will ask user if needed.", flush=True)

    # ── Auto knowledge feed — fetches fresh web content every hour ────────────
    feed_cfg = settings.knowledge_feed
    feed_interval = int(feed_cfg.get("interval_minutes", 60)) * 60
    feed_feeds = feed_cfg.get("feeds") or None  # None = use defaults
    knowledge_scheduler = KnowledgeFeedScheduler(mem, interval_seconds=feed_interval, feeds=feed_feeds)
    knowledge_scheduler.start()
    app.state.knowledge_scheduler = knowledge_scheduler

    # ── Web Watcher — user-defined topic refresh (once per hour) ─────────────
    watcher_scheduler = WatcherScheduler(mem, interval_seconds=3600)
    watcher_scheduler.start()
    app.state.watcher_scheduler = watcher_scheduler

    # Pre-warm Kokoro in the background — don't block Uvicorn from starting.
    # The first voice request will wait if it arrives before warm-up finishes,
    # but the server accepts connections immediately.
    tts_engine = settings.voice.get("tts", {}).get("engine", "macos_say")
    if tts_engine == "kokoro":
        import asyncio
        from gaaia.server.routers.voice import warmup_kokoro_inference
        print("[GAIA] Pre-warming Kokoro TTS (runs in background)...", flush=True)

        async def _warm_kokoro() -> None:
            # warmup_kokoro_inference is synchronous and potentially slow (model load +
            # first inference), so run it in a thread to avoid blocking the event loop.
            await asyncio.to_thread(warmup_kokoro_inference, settings)

        asyncio.create_task(_warm_kokoro())

    yield

    # ── Shutdown ───────────────────────────────────────────────────────────────
    try:
        knowledge_scheduler.stop()
    except Exception:
        pass
    try:
        watcher_scheduler.stop()
    except Exception:
        pass

    # Do NOT clear chat history, face DB, or voice profiles on exit — that data lives under
    # `app.data_dir` and must survive application restarts. (Previously this block wiped
    # everything on every shutdown; opt-in with GAIA_WIPE_DATA_ON_EXIT=1 for a clean test slate.)
    if os.environ.get("GAIA_WIPE_DATA_ON_EXIT", "").lower() in ("1", "true", "yes"):
        try:
            app.state.memory.clear_all()
        except Exception as exc:
            print(f"[GAIA] Memory clear on exit: {exc}", flush=True)
        try:
            face_store = getattr(app.state, "face_identity", None)
            if face_store is not None:
                import shutil
                fpath = face_store.db_path
                if fpath.exists():
                    shutil.rmtree(fpath, ignore_errors=True)
                    fpath.mkdir(parents=True, exist_ok=True)
                print("[GAIA] Face data wiped (GAIA_WIPE_DATA_ON_EXIT).", flush=True)
        except Exception as exc:
            print(f"[GAIA] Face wipe on exit: {exc}", flush=True)
        try:
            import gaaia.server.routers.voice as _vr
            if _vr._speaker_identity is not None:  # noqa: SLF001
                _vr._speaker_identity._profiles = {}
                _vr._speaker_identity._counter = 0
                if _vr._speaker_identity._path.exists():
                    _vr._speaker_identity._path.unlink()
            print("[GAIA] Voice profile file wiped (GAIA_WIPE_DATA_ON_EXIT).", flush=True)
        except Exception as exc:
            print(f"[GAIA] Voice wipe on exit: {exc}", flush=True)


def create_app() -> FastAPI:
    app = FastAPI(
        title="GAAIA API",
        version="0.1.0",
        description="GAAIA — Gopaul Advanced Artificial Intelligence & Automation — local REST + SSE",
        lifespan=lifespan,
    )

    # Security headers on every response (XSS, clickjacking, CSP, etc.)
    app.add_middleware(SecurityHeadersMiddleware)

    # Allow the desktop UI (same machine); credentials=True required for cookie auth
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["http://localhost:3000", "http://127.0.0.1:3000",
                       "http://localhost:8765", "http://127.0.0.1:8765"],
        allow_methods=["GET", "POST", "PATCH", "PUT", "DELETE", "OPTIONS"],
        allow_headers=["Content-Type", "Authorization", "X-Requested-With"],
        allow_credentials=True,
    )

    app.include_router(agents.router,      prefix="/agents",          tags=["Agents"])
    app.include_router(debate.router,      prefix="/debate",          tags=["Debate"])
    app.include_router(podcast.router,     prefix="/podcast",         tags=["Podcast"])
    app.include_router(auth.router,        prefix="/auth",            tags=["Auth"])
    app.include_router(oauth.router,       prefix="/auth/oauth",      tags=["OAuth"])
    app.include_router(chat.router,       prefix="/chat",       tags=["Chat"])
    app.include_router(education.router,  prefix="/education",  tags=["Education"])
    app.include_router(voice.router,  prefix="/voice",  tags=["Voice"])
    app.include_router(memory.router, prefix="/memory", tags=["Memory"])
    app.include_router(camera.router, prefix="/camera", tags=["Camera"])
    app.include_router(stats.router,  prefix="/stats",  tags=["Stats"])
    app.include_router(music.router,    prefix="/music",    tags=["Music"])
    app.include_router(image.router,    prefix="/image",    tags=["Image"])
    app.include_router(document.router, prefix="/document", tags=["Document"])
    app.include_router(chart.router,    prefix="/chart",    tags=["Chart"])
    app.include_router(watcher.router,  prefix="/watcher",  tags=["Watcher"])
    app.include_router(screen.router,   prefix="/screen",   tags=["Screen"])
    app.include_router(video.router,    prefix="/video",    tags=["Video"])

    @app.get("/health")
    def health() -> dict:
        return {"status": "ok", "model": app.state.settings.model.get("name")}

    return app

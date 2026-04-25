"""
GAAIA Model Router — selects the best available model for each role based on
system RAM and which models are actually installed in Ollama.

Called once at startup; results are stored in settings._effective_model_overrides
so every router transparently gets the right model without any changes.
"""

from __future__ import annotations

import re
from typing import Any

# ── RAM requirements per model (GB, approximate for Ollama default quant) ─────
# Covers the full Q4/Q8 range. Unrecognised models default to 8 GB (safe-ish).
_MODEL_RAM_GB: dict[str, float] = {
    # ── Sub-3 B ───────────────────────────────────────────────────────────────
    "tinyllama": 1.0,       "tinydolphin": 1.0,
    "smollm2": 1.0,         "smollm": 1.0,
    "llama3.2:1b": 1.0,     "qwen2.5:1.5b": 1.5,
    "phi:2.7b": 2.0,        "phi": 2.0,
    "phi3:mini": 2.0,       "gemma2:2b": 2.0,
    "llama3.2:3b": 2.5,     "qwen2.5:3b": 2.5,
    "deepseek-r1:1.5b": 1.5,

    # ── 4 B ───────────────────────────────────────────────────────────────────
    "gemma3:4b": 3.5,       "phi3:medium": 3.5,

    # ── 7–9 B ─────────────────────────────────────────────────────────────────
    "mistral:7b": 5.0,      "mistral:latest": 5.0,   "mistral": 5.0,
    "llama3.1:8b": 6.0,     "llama3:8b": 6.0,        "llama3.1": 6.0,
    "llama3.2:8b": 6.0,
    "qwen2.5:7b": 5.0,      "qwen2.5-coder:7b": 5.0,
    "gemma3:9b": 7.0,       "gemma2:9b": 7.0,        "gemma3:latest": 7.0,
    "neural-chat:7b": 5.0,  "zephyr:7b": 5.0,        "openchat:7b": 5.0,
    "orca-mini:7b": 5.0,    "starling-lm:7b": 5.0,   "mathstral:7b": 5.0,
    "deepseek-r1:7b": 5.0,  "deepseek-r1:8b": 6.0,
    "phi3": 6.0,

    # ── 11–14 B ───────────────────────────────────────────────────────────────
    "llama3.2-vision:11b": 9.0,  "llama3.2-vision": 9.0,
    "nous-hermes:13b": 9.0,      "codellama:13b": 9.0,

    # ── 27–34 B ───────────────────────────────────────────────────────────────
    "gemma3:27b": 18.0,     "gemma2:27b": 18.0,
    "qwen2.5:32b": 22.0,    "qwen2.5-coder:32b": 22.0,
    "codellama:34b": 24.0,  "deepseek-r1:32b": 22.0,
    "phi4": 10.0,           "phi4:14b": 10.0,

    # ── MoE (8×7B / 8×22B) ───────────────────────────────────────────────────
    "dolphin-mixtral:8x7b": 32.0, "mixtral:8x7b": 32.0,
    "mixtral:8x22b": 64.0,

    # ── 70–72 B ───────────────────────────────────────────────────────────────
    "qwen2.5:72b": 47.0,    "llama3.1:70b": 48.0,
    "llama3.3:70b": 48.0,   "llama3:70b": 48.0,
    "deepseek-r1:70b": 50.0,
}

# ── Fallback chains per model role ────────────────────────────────────────────
# Ordered best → smallest. The router picks the first one that (a) fits in RAM
# and (b) is installed in Ollama.
_ROLE_FALLBACKS: dict[str, list[str]] = {
    # Main / Pro — deepest reasoning, full tool support
    "name": [
        "qwen2.5:72b", "llama3.3:70b", "llama3.1:70b",
        "qwen2.5:32b", "gemma3:27b", "deepseek-r1:32b",
        "qwen2.5:7b", "mistral:7b", "llama3.1:8b", "gemma3:9b",
        "gemma3:4b", "llama3.2:3b",
    ],
    # Heavy — same as main, aliased for heavy tasks
    "heavy_model": [
        "qwen2.5:72b", "llama3.3:70b", "llama3.1:70b",
        "qwen2.5:32b", "gemma3:27b", "deepseek-r1:32b",
        "qwen2.5:7b", "mistral:7b", "llama3.1:8b",
    ],
    # Core — everyday balanced queries, tool-capable
    "core_model": [
        "mistral:7b", "qwen2.5:7b", "llama3.1:8b", "gemma3:9b",
        "gemma3:4b", "llama3.2:3b", "phi:2.7b",
    ],
    # Fast / Spark — ultra-fast voice & one-liners
    "fast_model": [
        "llama3.2:3b", "gemma3:4b", "phi:2.7b",
        "qwen2.5:3b", "tinyllama",
    ],
    # Swift / Air — light conversational, no tools
    "swift_model": [
        "gemma3:4b", "llama3.2:3b", "phi:2.7b",
        "qwen2.5:3b",
    ],
    # Code — coding specialist
    "code_model": [
        "qwen2.5-coder:32b", "deepseek-r1:32b", "qwen2.5:32b",
        "qwen2.5-coder:7b", "qwen2.5:7b", "mistral:7b",
        "llama3.1:8b", "gemma3:9b",
    ],
    # Vision — image & scene understanding
    "vision_model": [
        "llama3.2-vision:11b", "llama3.2-vision",
        # Fallback: vision requires a multimodal model; non-vision models get a note
    ],
    # Mind — deep nuanced chat, no tool calls
    "mind_model": [
        "gemma3:27b", "qwen2.5:32b", "deepseek-r1:32b",
        "gemma3:9b", "qwen2.5:7b", "mistral:7b",
    ],
    # Creative — writing, brainstorming
    "creative_model": [
        "dolphin-mixtral:8x7b", "qwen2.5:32b", "gemma3:27b",
        "mistral:7b", "qwen2.5:7b", "gemma3:9b",
    ],
    # Insight — focused analysis & reasoning
    "insight_model": [
        "zephyr:7b", "mistral:7b", "qwen2.5:7b",
        "llama3.1:8b", "gemma3:9b",
    ],
    # Sage — instruction following
    "sage_model": [
        "nous-hermes:13b", "mistral:7b", "qwen2.5:7b",
        "llama3.1:8b", "gemma3:9b",
    ],
    # Chat — friendly conversational
    "chat_model": [
        "neural-chat:7b", "mistral:7b", "gemma3:4b",
        "llama3.2:3b",
    ],
    # Logic — concise logical tasks
    "logic_model": [
        "orca-mini:7b", "mistral:7b", "qwen2.5:7b",
        "gemma3:4b",
    ],
    # Mini — smallest & snappiest
    "mini_model": [
        "phi:2.7b", "llama3.2:3b", "gemma3:4b",
        "qwen2.5:3b", "tinyllama",
    ],
    # Star — polished general responses
    "star_model": [
        "starling-lm:7b", "mistral:7b", "qwen2.5:7b",
        "gemma3:4b",
    ],
    # Open — openchat baseline
    "open_model": [
        "openchat:7b", "mistral:7b", "qwen2.5:7b",
        "gemma3:4b",
    ],
    # Quant — maths & statistics
    "quant_model": [
        "mathstral:7b", "qwen2.5:7b", "deepseek-r1:7b",
        "mistral:7b", "llama3.1:8b",
    ],
    # Reason — chain-of-thought & proofs
    "reason_model": [
        "deepseek-r1:70b", "deepseek-r1:32b", "deepseek-r1:7b",
        "qwen2.5:32b", "qwen2.5:7b", "mistral:7b",
    ],
}

# ── Tier labels shown in logs / UI ────────────────────────────────────────────
_ROLE_LABELS: dict[str, str] = {
    "name":           "GAIA Pro (main)",
    "heavy_model":    "GAIA Pro (heavy tasks)",
    "core_model":     "GAIA Core",
    "fast_model":     "GAIA Spark",
    "swift_model":    "GAIA Air",
    "code_model":     "GAIA Code",
    "vision_model":   "GAIA Vision",
    "mind_model":     "GAIA Mind",
    "creative_model": "GAIA Creative",
    "insight_model":  "GAIA Insight",
    "sage_model":     "GAIA Sage",
    "chat_model":     "GAAIA Chat",
    "logic_model":    "GAIA Logic",
    "mini_model":     "GAIA Mini",
    "star_model":     "GAIA Star",
    "open_model":     "GAIA Open",
    "quant_model":    "GAIA Quant",
    "reason_model":   "GAIA Reason",
}


def get_total_ram_gb() -> float:
    """Return total system RAM in GB (not available, total — Ollama loads into unified memory)."""
    try:
        import psutil  # type: ignore
        return psutil.virtual_memory().total / (1024 ** 3)
    except Exception:
        return 16.0  # conservative fallback — assume 16 GB if psutil missing


def _base_name(model: str) -> str:
    """Strip tag suffix for fuzzy matching: 'qwen2.5:72b' → 'qwen2.5:72b' (exact first)."""
    return model.strip().lower()


def _ram_for_model(model: str) -> float:
    """Return estimated RAM requirement for a model in GB."""
    key = _base_name(model)
    if key in _MODEL_RAM_GB:
        return _MODEL_RAM_GB[key]
    # Fuzzy: strip tag and try base name
    base = key.split(":")[0]
    if base in _MODEL_RAM_GB:
        return _MODEL_RAM_GB[base]
    # Heuristic from parameter count in name
    m = re.search(r"(\d+(?:\.\d+)?)\s*[bB]\b", key)
    if m:
        params = float(m.group(1))
        if params <= 1:   return 1.0
        if params <= 3:   return 2.5
        if params <= 4:   return 3.5
        if params <= 8:   return 6.0
        if params <= 14:  return 10.0
        if params <= 27:  return 18.0
        if params <= 34:  return 24.0
        if params <= 72:  return 48.0
        return 60.0
    return 8.0  # unknown — assume 8 GB


def get_installed_models(host: str = "http://localhost:11434") -> set[str]:
    """Query Ollama for locally installed models. Returns a set of 'name:tag' strings."""
    try:
        import ollama
        client = ollama.Client(host=host, timeout=5)
        response = client.list()
        models = response.get("models") or []
        names: set[str] = set()
        for m in models:
            raw = (m.get("name") or m.get("model") or "").strip().lower()
            if raw:
                names.add(raw)
                # also add without tag so "mistral" matches "mistral:7b"
                names.add(raw.split(":")[0])
        return names
    except Exception as exc:
        print(f"[ModelRouter] Could not query Ollama models: {exc}", flush=True)
        return set()


def _is_installed(model: str, installed: set[str]) -> bool:
    key = model.strip().lower()
    if key in installed:
        return True
    if key.split(":")[0] in installed:
        return True
    return False


def _fits_in_ram(model: str, available_gb: float, safety_margin_gb: float = 2.0) -> bool:
    """True if the model's RAM requirement fits within available RAM minus a safety margin."""
    return _ram_for_model(model) <= (available_gb - safety_margin_gb)


def select_model_for_role(
    role: str,
    configured_model: str,
    available_ram_gb: float,
    installed: set[str],
) -> tuple[str, str | None]:
    """
    Return (effective_model, reason_if_changed).

    Priority:
    1. If the configured model fits in RAM AND is installed → use it.
    2. Walk the fallback chain for the role:
       - Pick the first model that fits in RAM AND is installed.
    3. If nothing in the fallback chain is installed, pick the first that fits in RAM
       (user will need to pull it — log a hint).
    4. If literally nothing fits (< 2 GB headroom), return the smallest known model.
    """
    fits = _fits_in_ram(configured_model, available_ram_gb)
    installed_ok = _is_installed(configured_model, installed)

    if fits and installed_ok:
        return configured_model, None  # perfect — no change

    reasons: list[str] = []
    if not fits:
        need = _ram_for_model(configured_model)
        reasons.append(
            f"{configured_model} needs ~{need:.0f} GB but system has {available_ram_gb:.0f} GB RAM"
        )
    if not installed_ok:
        reasons.append(f"{configured_model} is not installed in Ollama")

    # Try fallback chain
    fallbacks = _ROLE_FALLBACKS.get(role, [])
    # Prefer installed models first, then any that fit
    for candidate in fallbacks:
        if _fits_in_ram(candidate, available_ram_gb) and _is_installed(candidate, installed):
            return candidate, f"Replaced {configured_model} ({'; '.join(reasons)}) → {candidate}"

    # Nothing installed fits — return first that fits (with install hint)
    for candidate in fallbacks:
        if _fits_in_ram(candidate, available_ram_gb):
            return candidate, (
                f"Replaced {configured_model} ({'; '.join(reasons)}) → {candidate} "
                f"(run: ollama pull {candidate})"
            )

    # Absolute last resort
    fallback = "llama3.2:3b"
    return fallback, f"No suitable model found for role '{role}'; defaulting to {fallback}"


def build_effective_model_config(
    model_cfg: dict[str, Any],
    available_ram_gb: float,
    installed: set[str],
) -> tuple[dict[str, str], list[str]]:
    """
    Given the YAML model config, return:
      - overrides dict: { role_key: effective_model_name, ... } for any roles that changed
      - log_lines: human-readable list of what changed and why

    Only roles that map to an actual model name string are processed.
    """
    overrides: dict[str, str] = {}
    log_lines: list[str] = []

    skip_keys = {
        "provider", "host", "keep_alive",
        "default_num_ctx", "default_num_predict", "top_p", "top_k",
        "code_num_ctx", "code_num_predict", "code_temperature",
        "heavy_num_ctx", "heavy_num_predict", "heavy_temperature",
        "quant_num_ctx", "quant_num_predict", "quant_temperature",
        "reason_num_ctx", "reason_num_predict", "reason_temperature",
        "image_high_accuracy_mode", "image_ocr_enabled",
        "image_analysis_progress", "max_tokens", "temperature",
        "core_temperature", "swift_temperature", "fast_temperature",
        "tool_choice",
    }

    for key, value in model_cfg.items():
        if key in skip_keys or not isinstance(value, str):
            continue
        if not value.strip():
            continue

        effective, reason = select_model_for_role(
            role=key,
            configured_model=value,
            available_ram_gb=available_ram_gb,
            installed=installed,
        )

        if reason:
            overrides[key] = effective
            label = _ROLE_LABELS.get(key, key)
            log_lines.append(f"  [{label}] {reason}")
        # else: model is fine — no override needed

    return overrides, log_lines


def run_model_routing(
    model_cfg: dict[str, Any],
    host: str = "http://localhost:11434",
) -> tuple[dict[str, str], float, set[str], list[str]]:
    """
    Entry point called at server startup.
    Returns (overrides, ram_gb, installed_set, log_lines).
    """
    ram_gb = get_total_ram_gb()
    installed = get_installed_models(host)
    overrides, log_lines = build_effective_model_config(model_cfg, ram_gb, installed)
    return overrides, ram_gb, installed, log_lines

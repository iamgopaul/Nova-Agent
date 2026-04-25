"""
Image generation service — tiered multi-model with automatic quality selection.

Tier selection (best-to-fallback, chosen at first use based on free RAM):

  Tier 3 — SDXL Lightning (ByteDance, Apache 2.0)
    · Stable Diffusion XL distilled to 4 steps, 1024 × 1024 output
    · ~7 GB download (SDXL base FP16 + small Lightning LoRA)
    · Requires ≥ 8 GB free RAM / unified memory
    · Dramatically better quality, coherence, and detail than SD 1.5

  Tier 2 — Dreamlike Photoreal 2.0  (dreamlike-art, CC BY-NC 4.0)
    · SD 1.5 fine-tune focused on photorealistic images
    · ~4 GB download, same pipeline as SD 1.5
    · Requires ≥ 4 GB free RAM
    · Significantly sharper, more lifelike results than base SD 1.5

  Tier 1 — Stable Diffusion v1.5  (RunwayML, CreativeML Open RAIL-M)
    · Always-works fallback, same ~4 GB, any hardware

All tiers use DPM++ 2M Karras for SD 1.5 models, and EulerDiscrete (trailing)
for SDXL Lightning — both far superior to the old default PNDM scheduler.
"""

from __future__ import annotations

import io
import logging
import random
import threading

import psutil

logger = logging.getLogger(__name__)

# ── Global pipeline state ────────────────────────────────────────────────────

_pipe        = None
_pipe_device: str | None = None   # "cpu" | "mps" | "cuda"
_pipe_type: str | None   = None   # "sd15" | "sdxl"

_lock           = threading.Lock()  # guards model loading (one-time)
_inference_lock = threading.Lock()  # guards inference — pipeline is not thread-safe

# Img2img pipeline — lazily initialized from same model weights (zero extra download)
_img2img_pipe      = None
_img2img_lock      = threading.Lock()

# ── Model IDs ────────────────────────────────────────────────────────────────

_SDXL_BASE_ID       = "stabilityai/stable-diffusion-xl-base-1.0"
_SDXL_LIGHTNING_REPO = "ByteDance/SDXL-Lightning"
_SDXL_LIGHTNING_CKPT = "sdxl_lightning_4step_lora.safetensors"  # ~290 MB LoRA

_DREAMLIKE_ID = "dreamlike-art/dreamlike-photoreal-2.0"   # SD 1.5 fine-tune
_SD15_ID      = "runwayml/stable-diffusion-v1-5"          # always-works fallback

# ── Negative prompts ─────────────────────────────────────────────────────────

# Core quality negatives — always applied regardless of style
_NEGATIVE_CORE = (
    "blurry, low quality, low resolution, worst quality, bad quality, "
    "bad anatomy, poorly drawn face, poorly drawn hands, bad hands, "
    "extra fingers, missing fingers, mutated hands, extra limbs, missing limbs, "
    "disfigured, deformed, distorted, ugly, morbid, mutation, mutated, "
    "watermark, text, signature, username, artist name, logo, "
    "jpeg artifacts, noise, grain, pixelated, grainy, aliasing, "
    "pixel art, 8-bit, 16-bit, pixel, mosaic, tiled, low-res sprite, "
    "out of focus, blurry background, soft focus, haze, "
    "overexposed, underexposed, washed out, oversaturated, "
    "bad proportions, bad composition, cropped, frame, border, "
    "cluttered, chaotic composition, too many objects, busy background"
)

# Always appended unless the request explicitly asks for a sketch/pencil/grayscale style
_NEGATIVE_COLOR_BLOCK = (
    ", grayscale, monochrome, black and white, greyscale, black-and-white, "
    "desaturated, colorless, faded colors, washed out colors"
)

# Added only for realistic/photographic requests (blocks stylised rendering)
_NEGATIVE_REALISM_EXTRA = ", cartoon, anime, sketch, illustration, 3d render, cgi, flat color"

# Added only for anime/cartoon requests (blocks photorealistic rendering)
_NEGATIVE_ANIME_EXTRA = ", photorealistic, realistic, photograph, real person, 3d render, cgi"

# Default (neutral) — no style exclusions
_DEFAULT_NEGATIVE = _NEGATIVE_CORE

# Style keywords that indicate the user wants anime / illustrated output
_ANIME_STYLE_KEYWORDS = frozenset({
    "anime", "manga", "cartoon", "animated", "one piece", "naruto", "bleach",
    "dragonball", "dragon ball", "attack on titan", "demon slayer", "jujutsu",
    "studio ghibli", "chibi", "shounen", "shonen", "shojo", "kawaii",
    "illustrated", "illustration", "comic", "cel shaded",
})

# Style keywords that indicate the user wants photorealistic output
_REALISTIC_STYLE_KEYWORDS = frozenset({
    "realistic", "photorealistic", "real", "photograph", "photo",
    "hyperrealistic", "lifelike", "live action",
})

# ── Artistic style detection ──────────────────────────────────────────────────
# Each entry: (keyword_set, prefix_to_add, quality_suffix)
_SKETCH_KEYWORDS    = frozenset({"sketch", "pencil sketch", "pencil drawing", "hand drawn", "hand-drawn", "line art", "lineart", "line drawing", "charcoal", "charcoal drawing", "ink drawing", "ink sketch"})
_WATERCOLOR_KEYWORDS = frozenset({"watercolor", "watercolour", "watercolor painting", "aquarelle", "wash painting"})
_OIL_KEYWORDS       = frozenset({"oil painting", "oil paint", "oil on canvas", "classical painting", "baroque", "renaissance painting"})
_VECTOR_KEYWORDS    = frozenset({"vector art", "vector illustration", "flat illustration", "flat design", "svg style", "minimalist flat", "adobe illustrator style"})
_PIXEL_KEYWORDS     = frozenset({"pixel art", "8-bit", "16-bit", "retro game", "sprite", "pixelated"})
_CONCEPT_KEYWORDS   = frozenset({"concept art", "concept design", "game art", "art station", "artstation", "digital painting", "matte painting"})
_PHOTOGRAPHY_KEYWORDS = frozenset({"portrait photography", "landscape photography", "street photography", "macro photography", "bokeh", "depth of field", "dslr", "35mm", "film photography"})

# Style → (injected prefix, quality suffix for SD1.5, quality suffix for SDXL)
_STYLE_MAP = {
    "sketch": (
        "detailed pencil sketch, fine linework, graphite on white paper,",
        "intricate linework, masterpiece sketch, highly detailed, white background",
        "intricate linework, ultra detailed sketch, white background, high resolution",
    ),
    "watercolor": (
        "beautiful watercolor painting, soft washes, wet on wet technique,",
        "vibrant watercolor, artistic brushstrokes, paper texture, masterpiece",
        "vibrant watercolor, ultra detailed, soft gradients, high resolution",
    ),
    "oil_painting": (
        "oil painting on canvas, rich textures, impasto technique,",
        "masterpiece oil painting, dramatic lighting, rich colors, highly detailed",
        "oil painting masterpiece, ultra detailed, dramatic lighting, high resolution",
    ),
    "vector": (
        "flat vector illustration, clean geometric shapes, bold outlines,",
        "crisp clean edges, vibrant flat colors, professional graphic design, no gradients",
        "professional vector art, ultra clean, bold colors, high resolution",
    ),
    "pixel_art": (
        "pixel art, 16-bit style, crisp pixels,",
        "detailed pixel art, vibrant pixel colors, masterpiece retro game art",
        "ultra detailed pixel art, vibrant, high resolution sprite",
    ),
    "concept_art": (
        "professional concept art, highly detailed, dramatic composition,",
        "artstation trending, cinematic lighting, ultra detailed, 8k",
        "artstation masterpiece, cinematic 8k, ultra detailed",
    ),
    "photography": (
        "professional photography, sharp focus, bokeh,",
        "DSLR photo, 35mm lens, natural lighting, ultra sharp, 8k",
        "professional photo, sharp focus, natural lighting, 8k, ultra detailed",
    ),
}


def _detect_artistic_style(prompt: str) -> str | None:
    """Return a style key from _STYLE_MAP if the prompt requests an artistic style."""
    lowered = prompt.lower()
    if any(k in lowered for k in _SKETCH_KEYWORDS):
        return "sketch"
    if any(k in lowered for k in _WATERCOLOR_KEYWORDS):
        return "watercolor"
    if any(k in lowered for k in _OIL_KEYWORDS):
        return "oil_painting"
    if any(k in lowered for k in _VECTOR_KEYWORDS):
        return "vector"
    if any(k in lowered for k in _PIXEL_KEYWORDS):
        return "pixel_art"
    if any(k in lowered for k in _CONCEPT_KEYWORDS):
        return "concept_art"
    if any(k in lowered for k in _PHOTOGRAPHY_KEYWORDS):
        return "photography"
    return None


_SKETCH_STYLE_WORDS = frozenset({
    "sketch", "pencil", "graphite", "charcoal", "line art", "lineart",
    "ink drawing", "black and white", "grayscale", "monochrome",
})


def _build_negative_prompt(prompt: str, base_negative: str) -> str:
    """Return an appropriate negative prompt based on the detected style in *prompt*."""
    lowered = prompt.lower()
    wants_anime  = any(k in lowered for k in _ANIME_STYLE_KEYWORDS)
    wants_real   = any(k in lowered for k in _REALISTIC_STYLE_KEYWORDS)
    wants_sketch = any(k in lowered for k in _SKETCH_STYLE_WORDS)

    # Use the caller-supplied base only if it's substantial
    neg = base_negative if base_negative and len(base_negative) >= 50 else _NEGATIVE_CORE

    # Block grayscale/monochrome unless the user explicitly wants a sketch/pencil style
    if not wants_sketch:
        neg = neg + _NEGATIVE_COLOR_BLOCK

    if wants_anime and not wants_real:
        return neg + _NEGATIVE_ANIME_EXTRA
    if wants_real and not wants_anime:
        return neg + _NEGATIVE_REALISM_EXTRA
    # Ambiguous or no style hint — neutral core only
    return neg

# ── Prompt libraries ─────────────────────────────────────────────────────────

_RANDOM_PROMPTS = [
    "a breathtaking mountain landscape at golden hour, dramatic storm clouds, photorealistic",
    "a mystical ancient forest with bioluminescent plants and floating fireflies at night",
    "a futuristic neon-lit cyberpunk city street in the rain, vivid reflections on wet cobblestones",
    "a majestic ocean wave crashing on rugged rocky cliffs at sunrise, spray catching light",
    "a cozy autumn cabin deep in the woods, warm amber light glowing through frosted windows",
    "a vibrant tropical coral reef with exotic fish and sea turtles in crystal-clear water",
    "an epic fantasy dragon soaring over a medieval stone castle at dusk, wings spread wide",
    "a serene Japanese cherry blossom garden with a curved bridge over a mirror-still koi pond",
    "the aurora borealis shimmering in emerald and violet above a frozen mountain lake",
    "a vintage steampunk airship drifting above storm clouds at sunset, brass gears glowing",
]

_VAGUE_TERMS = frozenset({
    "", "image", "photo", "picture", "pic", "art", "drawing", "painting",
    "random image", "an image", "a photo", "a picture", "a painting",
    "random", "something", "something random", "anything",
    "a cool image", "a cool photo", "a cool picture",
    "random art", "some art", "some image", "some photo",
    "generate image", "generate photo",
})

_SD15_QUALITY_SUFFIX = (
    "(masterpiece:1.2), (best quality:1.1), (ultra detailed:1.1), "
    "sharp focus, vibrant colors, 8k uhd"
)

# Anime-specific quality tags that work well with SD 1.5 / Dreamlike
_SD15_ANIME_SUFFIX = (
    "(masterpiece:1.3), (best quality:1.2), (highly detailed:1.2), "
    "beautiful detailed eyes, vibrant colors, official art, "
    "intricate details, sharp outlines, dynamic pose, 8k"
)

_SDXL_QUALITY_SUFFIX = (
    "ultra detailed, sharp focus, vibrant colors, 8k uhd, high resolution"
)

_SDXL_ANIME_SUFFIX = (
    "ultra detailed, beautiful detailed eyes, vibrant colors, "
    "official art, sharp outlines, dynamic pose, high resolution, 8k"
)

# ── Prompt enrichment ────────────────────────────────────────────────────────

def _enrich_prompt(prompt: str, pipe_type: str = "sd15") -> str:
    """Expand vague prompts; append style-aware quality boosters."""
    p = prompt.strip()
    lowered = p.lower()

    if lowered in _VAGUE_TERMS:
        chosen = random.choice(_RANDOM_PROMPTS)
        print(f"[ImageGen] Vague prompt → creative default: '{chosen[:60]}'", flush=True)
        suffix = _SDXL_QUALITY_SUFFIX if pipe_type == "sdxl" else _SD15_QUALITY_SUFFIX
        return f"{chosen}, {suffix}"

    quality_markers = ("masterpiece", "best quality", "ultra detailed", "8k", "photorealistic",
                       "digital art", "sharp focus", "official art", "uhd", "artstation",
                       "linework", "watercolor", "oil painting", "pixel art", "vector")
    already_has_quality = any(m in lowered for m in quality_markers)

    # ── Detect artistic style ─────────────────────────────────────────────────
    art_style = _detect_artistic_style(lowered)
    if art_style and art_style in _STYLE_MAP:
        prefix, sd15_sfx, sdxl_sfx = _STYLE_MAP[art_style]
        sfx = sdxl_sfx if pipe_type == "sdxl" else sd15_sfx
        # Inject style prefix if it's not already in the prompt
        if prefix.split(",")[0].strip() not in lowered:
            p = f"{prefix} {p}"
        if not already_has_quality:
            p = f"{p}, {sfx}"
        print(f"[ImageGen] Art style detected: {art_style}", flush=True)
        return p

    # ── Anime / illustrated style ─────────────────────────────────────────────
    is_anime = any(k in lowered for k in _ANIME_STYLE_KEYWORDS)
    if not already_has_quality:
        if pipe_type == "sdxl":
            suffix = _SDXL_ANIME_SUFFIX if is_anime else _SDXL_QUALITY_SUFFIX
        else:
            suffix = _SD15_ANIME_SUFFIX if is_anime else _SD15_QUALITY_SUFFIX
        p = f"{p}, {suffix}"

    # Ensure anime requests carry the style marker
    if is_anime and "anime" not in lowered:
        p = f"anime style, {p}"

    return p


# ── Scheduler helpers ────────────────────────────────────────────────────────

def _apply_dpm_scheduler(pipe) -> None:
    """DPM++ 2M Karras — much better than PNDM at same step count."""
    try:
        from diffusers import DPMSolverMultistepScheduler
        pipe.scheduler = DPMSolverMultistepScheduler.from_config(
            pipe.scheduler.config,
            algorithm_type="dpmsolver++",
            use_karras_sigmas=True,
        )
        print("[ImageGen] Scheduler → DPM++ 2M Karras.", flush=True)
    except Exception as e:
        print(f"[ImageGen] DPM++ scheduler swap failed ({e}), keeping default.", flush=True)


def _apply_euler_trailing(pipe) -> None:
    """EulerDiscrete with trailing timesteps — required for SDXL Lightning."""
    try:
        from diffusers import EulerDiscreteScheduler
        pipe.scheduler = EulerDiscreteScheduler.from_config(
            pipe.scheduler.config, timestep_spacing="trailing"
        )
        print("[ImageGen] Scheduler → Euler (trailing) for SDXL Lightning.", flush=True)
    except Exception as e:
        print(f"[ImageGen] Euler scheduler failed ({e}).", flush=True)


# ── Model loaders ────────────────────────────────────────────────────────────

def _device_and_dtype(force_cpu: bool = False):
    import torch
    if force_cpu:
        return "cpu", torch.float32
    if torch.cuda.is_available():
        return "cuda", torch.float16
    if hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        return "mps", torch.float32   # float16 → NaN / blank output on MPS for SD 1.5
    return "cpu", torch.float32


def _load_sd15_model(model_id: str, force_cpu: bool = False) -> tuple:
    """Load any SD 1.5-compatible model.  Returns (pipe, device, 'sd15')."""
    import torch
    from diffusers import StableDiffusionPipeline

    device, dtype = _device_and_dtype(force_cpu)
    print(f"[ImageGen] Loading SD 1.5 model: {model_id} on {device} ({dtype}) …", flush=True)

    pipe = StableDiffusionPipeline.from_pretrained(
        model_id,
        torch_dtype=dtype,
        safety_checker=None,
        requires_safety_checker=False,
    ).to(device)

    _apply_dpm_scheduler(pipe)
    pipe.enable_attention_slicing()
    try:
        pipe.enable_vae_slicing()
    except Exception:
        pass
    if device == "cpu":
        pipe.enable_sequential_cpu_offload()

    print(f"[ImageGen] {model_id.split('/')[-1]} ready on {device}.", flush=True)
    return pipe, device, "sd15"


def _load_sdxl_lightning(force_cpu: bool = False) -> tuple:
    """
    Load SDXL base + ByteDance Lightning LoRA (4-step, 1024 px).
    Downloads ~7 GB on first use; cached on subsequent runs.
    Returns (pipe, device, 'sdxl').
    """
    import torch
    from diffusers import StableDiffusionXLPipeline
    from huggingface_hub import hf_hub_download

    # SDXL Lightning works with float16 on MPS (unlike SD 1.5) — no NaN issue
    if force_cpu:
        device, dtype = "cpu", torch.float32
    elif torch.cuda.is_available():
        device, dtype = "cuda", torch.float16
    elif hasattr(torch.backends, "mps") and torch.backends.mps.is_available():
        device, dtype = "mps", torch.float16
    else:
        device, dtype = "cpu", torch.float32

    print(f"[ImageGen] Loading SDXL Lightning on {device} ({dtype}) …", flush=True)
    print(f"[ImageGen] First run: ~7 GB download (SDXL base + Lightning LoRA).", flush=True)

    pipe = StableDiffusionXLPipeline.from_pretrained(
        _SDXL_BASE_ID,
        torch_dtype=dtype,
        variant="fp16" if dtype == torch.float16 else None,
        use_safetensors=True,
    ).to(device)

    # Download and fuse the 4-step Lightning LoRA weights (~290 MB)
    lora_path = hf_hub_download(_SDXL_LIGHTNING_REPO, _SDXL_LIGHTNING_CKPT)
    pipe.load_lora_weights(lora_path)
    pipe.fuse_lora()

    _apply_euler_trailing(pipe)
    pipe.enable_attention_slicing()
    try:
        pipe.enable_vae_slicing()
    except Exception:
        pass

    print(f"[ImageGen] SDXL Lightning ready on {device} (4-step, 1024 px).", flush=True)
    return pipe, device, "sdxl"


# ── Tier selection ────────────────────────────────────────────────────────────

def _free_ram_gb() -> float:
    return psutil.virtual_memory().available / (1024 ** 3)


def _load_best(force_cpu: bool = False) -> tuple:
    """
    Pick and load the highest-quality tier that fits in available RAM.

      ≥ 8 GB free  →  SDXL Lightning (1024 px, 4 steps)
      ≥ 4 GB free  →  Dreamlike Photoreal 2.0 (640 px, 30 steps)
      fallback     →  Stable Diffusion v1.5   (640 px, 30 steps)
    """
    free_gb = _free_ram_gb()
    print(f"[ImageGen] Available RAM: {free_gb:.1f} GB", flush=True)

    if not force_cpu and free_gb >= 8.0:
        try:
            return _load_sdxl_lightning()
        except Exception as e:
            print(f"[ImageGen] SDXL Lightning failed ({e}) — trying Dreamlike Photoreal …", flush=True)

    if free_gb >= 4.0:
        try:
            return _load_sd15_model(_DREAMLIKE_ID, force_cpu=force_cpu)
        except Exception as e:
            print(f"[ImageGen] Dreamlike Photoreal failed ({e}) — using SD 1.5 fallback …", flush=True)

    return _load_sd15_model(_SD15_ID, force_cpu=force_cpu)


# ── Pipeline cache ────────────────────────────────────────────────────────────

def _get_pipe(force_cpu: bool = False) -> tuple:
    """Return (pipe, pipe_type), loading if needed."""
    global _pipe, _pipe_device, _pipe_type

    with _lock:
        reload = False
        if _pipe is None:
            reload = True
        elif force_cpu and _pipe_device != "cpu":
            print("[ImageGen] Switching to CPU fallback pipeline …", flush=True)
            _pipe = None
            reload = True
        elif _pipe_device == "mps" and _pipe_type == "sd15":
            # Verify MPS SD 1.5 pipe uses float32 (not old float16)
            try:
                import torch
                if next(_pipe.unet.parameters()).dtype != torch.float32:
                    print("[ImageGen] MPS SD 1.5 pipe is float16 — reloading …", flush=True)
                    _pipe = None
                    reload = True
            except Exception:
                pass

        if reload:
            _pipe, _pipe_device, _pipe_type = _load_best(force_cpu=force_cpu)

    return _pipe, _pipe_type


# ── Blank-image detector ─────────────────────────────────────────────────────

def _is_blank_image(image) -> bool:
    try:
        import numpy as np
        return float(np.array(image.convert("RGB")).std()) < 3.0
    except Exception:
        return False


# ── Public API ────────────────────────────────────────────────────────────────

def generate_image(
    prompt: str,
    negative_prompt: str = "",
    width: int = 640,
    height: int = 640,
    steps: int = 30,
    guidance_scale: float = 8.5,
) -> bytes:
    """
    Generate an image from *prompt* and return PNG bytes.

    The function automatically selects the best available pipeline tier:
      - SDXL Lightning → ignores width/height/steps/guidance (fixed: 1024 px, 4 steps)
      - Dreamlike / SD 1.5 → uses supplied parameters
    """
    import torch

    pipe, pipe_type = _get_pipe()

    # Upgrade the prompt with quality boosters (anime-aware)
    enriched = _enrich_prompt(prompt, pipe_type)

    # Build adaptive negative prompt — style-aware, never blocks the requested style
    negative_prompt = _build_negative_prompt(enriched, negative_prompt)

    if pipe_type == "sdxl":
        return _generate_sdxl(pipe, enriched)
    else:
        return _generate_sd15(pipe, enriched, negative_prompt, width, height, steps, guidance_scale)


def _generate_sdxl(pipe, prompt: str) -> bytes:
    """SDXL Lightning — fixed 4 steps, no CFG, 1024 × 1024."""
    import torch

    print(f"[ImageGen] SDXL Lightning: '{prompt[:100]}' (4 steps, 1024×1024) …", flush=True)

    generator = None
    if _pipe_device == "mps":
        try:
            generator = torch.Generator(device="cpu").manual_seed(random.randint(0, 2**32 - 1))
        except Exception:
            pass

    with _inference_lock:
        result = pipe(
            prompt=prompt,
            num_inference_steps=4,
            guidance_scale=0.0,    # Lightning distillation doesn't use CFG
            height=1024,
            width=1024,
            generator=generator,
        )

    image = result.images[0]

    if _is_blank_image(image):
        print("[ImageGen] SDXL Lightning produced blank — retrying with 8 steps …", flush=True)
        with _inference_lock:
            result2 = pipe(
                prompt=prompt,
                num_inference_steps=8,
                guidance_scale=0.0,
                height=1024,
                width=1024,
            )
        image = result2.images[0]

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    print(f"[ImageGen] SDXL Lightning done — {len(png_bytes) // 1024} KB PNG", flush=True)
    return png_bytes


def _generate_sd15(
    pipe, prompt: str, negative_prompt: str,
    width: int, height: int, steps: int, guidance_scale: float,
) -> bytes:
    """Dreamlike Photoreal 2.0 / SD 1.5 path."""
    import torch

    width  = min(768, max(256, (width  // 8) * 8))
    height = min(768, max(256, (height // 8) * 8))
    steps  = max(15, min(60, steps))

    print(
        f"[ImageGen] SD 1.5 ({_pipe_type}): '{prompt[:100]}' "
        f"({width}×{height}, {steps} steps, cfg={guidance_scale}) …",
        flush=True,
    )

    generator = None
    if _pipe_device == "mps":
        try:
            generator = torch.Generator(device="cpu").manual_seed(random.randint(0, 2**32 - 1))
        except Exception:
            pass

    with _inference_lock:
        result = pipe(
            prompt=prompt,
            negative_prompt=negative_prompt,
            width=width,
            height=height,
            num_inference_steps=steps,
            guidance_scale=guidance_scale,
            num_images_per_prompt=1,
            generator=generator,
        )

    image = result.images[0]

    if _is_blank_image(image):
        print("[ImageGen] Blank output — reloading on CPU and retrying …", flush=True)
        cpu_pipe, _ = _get_pipe(force_cpu=True)
        with _inference_lock:
            result2 = cpu_pipe(
                prompt=prompt,
                negative_prompt=negative_prompt,
                width=width,
                height=height,
                num_inference_steps=max(steps, 25),
                guidance_scale=guidance_scale,
                num_images_per_prompt=1,
            )
        image = result2.images[0]

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    print(f"[ImageGen] Done — {len(png_bytes) // 1024} KB PNG", flush=True)
    return png_bytes


# ── Img2img pipeline (shared weights — zero extra download) ──────────────────

def _get_img2img_pipe():
    """
    Return an img2img pipeline that SHARES the already-loaded model weights.
    No extra download — just wraps the same UNet/VAE/text-encoder.
    """
    global _img2img_pipe

    with _img2img_lock:
        if _img2img_pipe is not None:
            return _img2img_pipe, _pipe_type

        # Ensure the base txt2img pipe is loaded first
        pipe, pipe_type = _get_pipe()

        try:
            if pipe_type == "sdxl":
                from diffusers import StableDiffusionXLImg2ImgPipeline
                _img2img_pipe = StableDiffusionXLImg2ImgPipeline(**pipe.components)
            else:
                from diffusers import StableDiffusionImg2ImgPipeline
                _img2img_pipe = StableDiffusionImg2ImgPipeline(**pipe.components)

            _img2img_pipe.enable_attention_slicing()
            try:
                _img2img_pipe.enable_vae_slicing()
            except Exception:
                pass

            print(f"[ImageGen] Img2img pipeline ready (shared weights, {pipe_type}).", flush=True)
        except Exception as exc:
            print(f"[ImageGen] Img2img pipeline init failed: {exc}", flush=True)
            _img2img_pipe = None

    return _img2img_pipe, _pipe_type


def generate_image_variation(
    init_image_bytes: bytes,
    prompt: str,
    negative_prompt: str = "",
    strength: float = 0.75,
    steps: int = 25,
    guidance_scale: float = 7.5,
) -> bytes:
    """
    Generate a variation of *init_image_bytes* guided by *prompt*.

    strength controls how much the output deviates from the reference:
      0.0 = copy exactly (never use this)
      0.35 = visually grounded reference (for web reference images)
      0.65 = significant changes while preserving composition
      0.75 = strong changes, loose composition reference (follow-up edits)
      1.0  = ignore init image (same as txt2img)

    Falls back to txt2img if the img2img pipeline fails to load.
    """
    from PIL import Image as PILImage
    import torch

    img2img_pipe, pipe_type = _get_img2img_pipe()

    if img2img_pipe is None:
        print("[ImageGen] Img2img unavailable — falling back to txt2img", flush=True)
        return generate_image(prompt, negative_prompt)

    # Load and prepare reference image
    try:
        init_image = PILImage.open(io.BytesIO(init_image_bytes)).convert("RGB")
    except Exception as exc:
        print(f"[ImageGen] Failed to load init image: {exc} — falling back to txt2img", flush=True)
        return generate_image(prompt, negative_prompt)

    enriched = _enrich_prompt(prompt, pipe_type)
    neg      = _build_negative_prompt(enriched, negative_prompt)

    print(
        f"[ImageGen] Img2img ({pipe_type}): strength={strength:.2f}, "
        f"'{prompt[:80]}' …",
        flush=True,
    )

    try:
        if pipe_type == "sdxl":
            # SDXL img2img: resize to 1024, minimal steps since Lightning schedule is fixed
            init_image = init_image.resize((1024, 1024), PILImage.LANCZOS)
            effective_steps = max(4, int(20 * strength))
            with _inference_lock:
                result = img2img_pipe(
                    prompt=enriched,
                    image=init_image,
                    strength=strength,
                    num_inference_steps=effective_steps,
                    guidance_scale=max(guidance_scale, 3.0),
                )
        else:
            # SD 1.5 / Dreamlike img2img
            w, h = init_image.size
            w = min(768, max(256, (w // 8) * 8))
            h = min(768, max(256, (h // 8) * 8))
            init_image = init_image.resize((w, h), PILImage.LANCZOS)

            generator = None
            if _pipe_device == "mps":
                try:
                    generator = torch.Generator(device="cpu").manual_seed(
                        random.randint(0, 2**32 - 1)
                    )
                except Exception:
                    pass

            with _inference_lock:
                result = img2img_pipe(
                    prompt=enriched,
                    negative_prompt=neg,
                    image=init_image,
                    strength=strength,
                    num_inference_steps=steps,
                    guidance_scale=guidance_scale,
                    generator=generator,
                )

        image = result.images[0]

        if _is_blank_image(image):
            print("[ImageGen] Img2img blank output — falling back to txt2img", flush=True)
            return generate_image(prompt, negative_prompt)

    except Exception as exc:
        print(f"[ImageGen] Img2img failed ({exc}) — falling back to txt2img", flush=True)
        return generate_image(prompt, negative_prompt)

    buf = io.BytesIO()
    image.save(buf, format="PNG")
    png_bytes = buf.getvalue()
    print(f"[ImageGen] Img2img done — {len(png_bytes) // 1024} KB PNG", flush=True)
    return png_bytes

"""
Ollama vision model — single-frame scene description (hands come from MediaPipe elsewhere).
"""

from __future__ import annotations

import base64

CAMERA_VISION_PROMPT = (
    "You are a precise visual observer. Analyze this camera frame and report ONLY:\n\n"
    "1. FACE DIRECTION: Where is the person looking? "
    "(directly at camera / left / right / up / down / away)\n"
    "2. TEXT / OBJECTS: Read any visible text on clothing, signs, paper, or objects. "
    "List important held objects and notable background objects (up to 5).\n"
    "3. SCENE: One-line description of the overall scene if relevant.\n\n"
    "IMPORTANT: Do NOT mention hands, fingers, or finger counts at all — "
    "that information comes from a dedicated hand-tracking system.\n"
    "Format: short bullet points only. Skip any category with nothing notable."
)
CAMERA_VISION_TIMEOUT = 8.0


def describe_scene_frame(
    settings,
    image_bytes: bytes,
    timeout_sec: float | None = None,
) -> str:
    """Call the vision model on a raw camera JPEG and return a short scene description."""
    tlim = CAMERA_VISION_TIMEOUT if timeout_sec is None else timeout_sec
    try:
        import ollama

        vision_model = settings.model.get("vision_model", "llama3.2-vision:11b")
        if not vision_model:
            return ""
        image_b64 = base64.b64encode(image_bytes).decode("ascii")
        client = ollama.Client(host=settings.ollama_host)
        from concurrent.futures import ThreadPoolExecutor as _Pool

        pool = _Pool(max_workers=1)
        future = pool.submit(
            lambda: client.chat(
                model=vision_model,
                messages=[{"role": "user", "content": CAMERA_VISION_PROMPT, "images": [image_b64]}],
            )
        )
        result = future.result(timeout=tlim)
        return (getattr(getattr(result, "message", None), "content", "") or "").strip()
    except Exception as exc:
        print(f"[Nova] Camera vision error: {exc}")
        return ""

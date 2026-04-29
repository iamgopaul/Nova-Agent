"""
gaaia/services/model_client.py
──────────────────────────────
Thin abstraction over LLM backends.

Backends implement the same three methods (chat, chat_stream, list_models) so
call sites stay backend-agnostic:

  - OllamaBackend: local Ollama at :11434 (native /api/chat).
  - ExoBackend:    distributed exo cluster at :52415 (OpenAI-compatible /v1).
  - RouterBackend: holds both, dispatches per call. Big models go to exo when
                   it has them in its catalogue; everything else stays on
                   Ollama for low latency.

Message format follows Ollama's convention end-to-end:
    [{"role": "user", "content": "...", "images": [b64, ...]}]
ExoBackend translates `images` keys into OpenAI `image_url` content parts;
unknown options (num_ctx, top_k, etc.) are dropped because OpenAI's spec has
no equivalent.
"""

from __future__ import annotations

import json
import re
from typing import Iterator


def _extract_message_content(message_obj) -> str:
    """Pull `.content` from an Ollama message — handles typed and dict forms."""
    if message_obj is None:
        return ""
    content = getattr(message_obj, "content", None)
    if content is not None:
        return content or ""
    if isinstance(message_obj, dict):
        return message_obj.get("content") or ""
    return ""


# ─── Ollama backend ─────────────────────────────────────────────────────────────

class OllamaBackend:
    def __init__(self, host: str, timeout: float = 120.0) -> None:
        self._host = host
        self._timeout = timeout

    def _client(self):
        import ollama
        return ollama.Client(host=self._host, timeout=self._timeout)

    def chat(
        self,
        model: str,
        messages: list[dict],
        options: dict | None = None,
        keep_alive: str | None = None,
    ) -> str:
        kwargs: dict = {"model": model, "messages": messages, "options": options or {}}
        if keep_alive is not None:
            kwargs["keep_alive"] = keep_alive
        response = self._client().chat(**kwargs)
        msg = response.get("message") if isinstance(response, dict) else getattr(response, "message", None)
        return _extract_message_content(msg)

    def chat_stream(
        self,
        model: str,
        messages: list[dict],
        options: dict | None = None,
        keep_alive: str | None = None,
    ) -> Iterator[str]:
        kwargs: dict = {"model": model, "messages": messages, "stream": True, "options": options or {}}
        if keep_alive is not None:
            kwargs["keep_alive"] = keep_alive
        for chunk in self._client().chat(**kwargs):
            msg = chunk.get("message") if isinstance(chunk, dict) else getattr(chunk, "message", None)
            tok = _extract_message_content(msg)
            if tok:
                yield tok

    def list_models(self) -> set[str]:
        try:
            response = self._client().list()
            models = response.get("models") if isinstance(response, dict) else getattr(response, "models", None)
            models = models or []
            names: set[str] = set()
            for m in models:
                if isinstance(m, dict):
                    raw = (m.get("name") or m.get("model") or "").strip().lower()
                else:
                    raw = (getattr(m, "name", None) or getattr(m, "model", None) or "").strip().lower()
                if raw:
                    names.add(raw)
                    names.add(raw.split(":")[0])
            return names
        except Exception as exc:
            print(f"[ModelClient] Could not query Ollama models: {exc}", flush=True)
            return set()

    def chat_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        options: dict | None = None,
        keep_alive: str | None = None,
    ) -> tuple[str, list[dict]]:
        """Single-shot chat with tool definitions. Returns (content, normalized_tool_calls).
        Ollama does not assign ids to tool calls, so each call's id is None.
        """
        kwargs: dict = {
            "model": model,
            "messages": messages,
            "tools": tools,
            "options": options or {},
        }
        if keep_alive is not None:
            kwargs["keep_alive"] = keep_alive
        response = self._client().chat(**kwargs)
        msg = response.get("message") if isinstance(response, dict) else getattr(response, "message", None)
        content = _extract_message_content(msg)
        if msg is None:
            return content, []
        tool_calls_raw = msg.get("tool_calls") if isinstance(msg, dict) else getattr(msg, "tool_calls", None)
        if not tool_calls_raw:
            return content, []
        normalized: list[dict] = []
        for tc in tool_calls_raw:
            if isinstance(tc, dict):
                fn = tc.get("function") or {}
                name = fn.get("name") or ""
                args = fn.get("arguments")
            else:
                fn = getattr(tc, "function", None)
                name = getattr(fn, "name", "") if fn else ""
                args = getattr(fn, "arguments", None) if fn else None
            normalized.append(_normalize_tool_call(name, args, call_id=None))
        return content, normalized


# ─── Exo backend (OpenAI-compatible) ────────────────────────────────────────────

# Ollama option keys with no clean OpenAI equivalent — dropped on translation.
_EXO_DROP_OPTIONS = {"num_ctx", "top_k", "repeat_penalty", "seed", "stop", "keep_alive"}


def _ollama_options_to_openai(options: dict | None) -> dict:
    if not options:
        return {}
    out: dict = {}
    for k, v in options.items():
        if k in _EXO_DROP_OPTIONS:
            continue
        if k == "num_predict":
            out["max_tokens"] = v
        elif k in ("temperature", "top_p", "presence_penalty", "frequency_penalty"):
            out[k] = v
    return out


def _ollama_messages_to_openai(messages: list[dict]) -> list[dict]:
    """Ollama messages → OpenAI messages.

    Translates four shapes:
      - plain text   → unchanged role+content
      - `images: []` → `content` becomes a list of text+image_url parts
      - `tool_calls` on assistant → arguments dict serialized to JSON string,
        each call wrapped as {"id", "type": "function", "function": ...}
      - role=="tool" → `name` field becomes `tool_call_id` for OpenAI's spec
    """
    out: list[dict] = []
    for m in messages:
        role = m.get("role") or "user"

        if role == "tool":
            out.append({
                "role": "tool",
                "content": m.get("content") or "",
                "tool_call_id": m.get("tool_call_id") or m.get("name") or "",
            })
            continue

        tool_calls_in = m.get("tool_calls") or []
        if tool_calls_in:
            tcs_oai: list[dict] = []
            for tc in tool_calls_in:
                fn = tc.get("function") or {}
                args = fn.get("arguments")
                if isinstance(args, dict):
                    args_str = json.dumps(args)
                elif args is None:
                    args_str = "{}"
                else:
                    args_str = str(args)
                tcs_oai.append({
                    "id": tc.get("id") or "",
                    "type": "function",
                    "function": {"name": fn.get("name") or "", "arguments": args_str},
                })
            out.append({
                "role": role,
                "content": m.get("content") or "",
                "tool_calls": tcs_oai,
            })
            continue

        text = m.get("content") or ""
        images = m.get("images") or []
        if not images:
            out.append({"role": role, "content": text})
            continue
        parts: list[dict] = []
        if text:
            parts.append({"type": "text", "text": text})
        for img in images:
            url = img if isinstance(img, str) and img.startswith("data:") else f"data:image/jpeg;base64,{img}"
            parts.append({"type": "image_url", "image_url": {"url": url}})
        out.append({"role": role, "content": parts})
    return out


def _normalize_tool_call(name: str, arguments, call_id: str | None) -> dict:
    """Coerce a backend's tool_call into the facade's canonical dict shape:
    {"id": str|None, "function": {"name": str, "arguments": dict}}.
    """
    if isinstance(arguments, str):
        try:
            args_dict = json.loads(arguments) if arguments.strip() else {}
        except json.JSONDecodeError:
            args_dict = {}
    elif isinstance(arguments, dict):
        args_dict = arguments
    elif arguments is None:
        args_dict = {}
    else:
        args_dict = {}
    return {"id": call_id, "function": {"name": name or "", "arguments": args_dict}}


class ExoBackend:
    def __init__(self, host: str, timeout: float = 120.0) -> None:
        self._host = host.rstrip("/")
        self._timeout = timeout

    def _url(self, path: str) -> str:
        return f"{self._host}/v1{path}"

    def chat(
        self,
        model: str,
        messages: list[dict],
        options: dict | None = None,
        keep_alive: str | None = None,  # noqa: ARG002 — Ollama-only, ignored here
    ) -> str:
        import httpx
        body = {
            "model": model,
            "messages": _ollama_messages_to_openai(messages),
            **_ollama_options_to_openai(options),
        }
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(self._url("/chat/completions"), json=body)
            r.raise_for_status()
            data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return ""
        return (choices[0].get("message") or {}).get("content") or ""

    def chat_stream(
        self,
        model: str,
        messages: list[dict],
        options: dict | None = None,
        keep_alive: str | None = None,  # noqa: ARG002 — Ollama-only, ignored here
    ) -> Iterator[str]:
        import httpx
        body = {
            "model": model,
            "messages": _ollama_messages_to_openai(messages),
            "stream": True,
            **_ollama_options_to_openai(options),
        }
        with httpx.Client(timeout=self._timeout) as c:
            with c.stream("POST", self._url("/chat/completions"), json=body) as r:
                r.raise_for_status()
                for raw in r.iter_lines():
                    if not raw:
                        continue
                    line = raw.strip()
                    if not line.startswith("data:"):
                        continue
                    payload = line[5:].strip()
                    if payload == "[DONE]":
                        break
                    try:
                        chunk = json.loads(payload)
                    except json.JSONDecodeError:
                        continue
                    choices = chunk.get("choices") or []
                    if not choices:
                        continue
                    delta = choices[0].get("delta") or {}
                    tok = delta.get("content") or ""
                    if tok:
                        yield tok

    def list_models(self) -> set[str]:
        import httpx
        try:
            with httpx.Client(timeout=10.0) as c:
                r = c.get(self._url("/models"))
                r.raise_for_status()
                data = r.json()
            entries = data.get("data") or []
            return {(e.get("id") or "").strip().lower() for e in entries if e.get("id")}
        except Exception as exc:
            print(f"[ModelClient] Could not query exo models at {self._host}: {exc}", flush=True)
            return set()

    def chat_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        options: dict | None = None,
        keep_alive: str | None = None,  # noqa: ARG002 — Ollama-only, ignored here
    ) -> tuple[str, list[dict]]:
        """Single-shot chat with tools. Translates messages + tool calls between
        Ollama and OpenAI shapes. Real tool_call ids come back from the server."""
        import httpx
        body = {
            "model": model,
            "messages": _ollama_messages_to_openai(messages),
            "tools": tools,  # Ollama and OpenAI tool-definition shapes are identical
            **_ollama_options_to_openai(options),
        }
        with httpx.Client(timeout=self._timeout) as c:
            r = c.post(self._url("/chat/completions"), json=body)
            r.raise_for_status()
            data = r.json()
        choices = data.get("choices") or []
        if not choices:
            return "", []
        msg = choices[0].get("message") or {}
        content = msg.get("content") or ""
        tool_calls_raw = msg.get("tool_calls") or []
        normalized: list[dict] = []
        for tc in tool_calls_raw:
            fn = tc.get("function") or {}
            normalized.append(
                _normalize_tool_call(
                    fn.get("name") or "",
                    fn.get("arguments"),
                    call_id=tc.get("id") or "",
                )
            )
        return content, normalized


# ─── Router backend ─────────────────────────────────────────────────────────────

def _ram_cost_gb(model: str) -> float:
    """Heuristic RAM estimate from the parameter count in the model name."""
    key = model.strip().lower()
    m = re.search(r"(\d+(?:\.\d+)?)\s*[bB]\b", key)
    if m:
        params = float(m.group(1))
        if params <= 1: return 1.0
        if params <= 3: return 2.5
        if params <= 4: return 3.5
        if params <= 8: return 6.0
        if params <= 14: return 10.0
        if params <= 27: return 18.0
        if params <= 34: return 24.0
        if params <= 72: return 48.0
        return 60.0
    return 8.0


class RouterBackend:
    """
    Holds an OllamaBackend and an ExoBackend, dispatches per call.

    Routing rule: model RAM cost ≥ threshold AND model is in exo's catalogue
    → exo. Otherwise → Ollama. The exo catalogue is fetched lazily and cached;
    if exo is unreachable on first probe the router pins itself to Ollama for
    the remainder of the process.
    """

    def __init__(self, ollama: OllamaBackend, exo: ExoBackend, threshold_gb: float) -> None:
        self._ollama = ollama
        self._exo = exo
        self._threshold = threshold_gb
        self._exo_models: set[str] | None = None
        self._exo_disabled = False

    def _exo_has(self, model: str) -> bool:
        if self._exo_disabled:
            return False
        if self._exo_models is None:
            self._exo_models = self._exo.list_models()
            if not self._exo_models:
                self._exo_disabled = True
                return False
        return model.strip().lower() in self._exo_models

    def _pick(self, model: str):
        if _ram_cost_gb(model) >= self._threshold and self._exo_has(model):
            return self._exo
        return self._ollama

    def chat(
        self,
        model: str,
        messages: list[dict],
        options: dict | None = None,
        keep_alive: str | None = None,
    ) -> str:
        return self._pick(model).chat(model, messages, options, keep_alive=keep_alive)

    def chat_stream(
        self,
        model: str,
        messages: list[dict],
        options: dict | None = None,
        keep_alive: str | None = None,
    ) -> Iterator[str]:
        yield from self._pick(model).chat_stream(model, messages, options, keep_alive=keep_alive)

    def list_models(self) -> set[str]:
        models = set(self._ollama.list_models())
        if not self._exo_disabled:
            models |= self._exo.list_models()
        return models

    def chat_with_tools(
        self,
        model: str,
        messages: list[dict],
        tools: list[dict],
        options: dict | None = None,
        keep_alive: str | None = None,
    ) -> tuple[str, list[dict]]:
        return self._pick(model).chat_with_tools(
            model, messages, tools, options, keep_alive=keep_alive
        )


# ─── Factory ────────────────────────────────────────────────────────────────────

def get_model_client(host: str = "http://localhost:11434", timeout: float = 600.0):
    """
    Build a ModelClient from current settings. If exo_enabled is set, returns
    a RouterBackend wrapping Ollama + exo. Otherwise returns plain OllamaBackend.
    """
    ollama = OllamaBackend(host=host, timeout=timeout)
    try:
        from config.settings import get_settings
        settings = get_settings()
    except Exception:
        return ollama
    if not getattr(settings, "exo_enabled", False):
        return ollama
    exo = ExoBackend(host=settings.exo_host, timeout=timeout)
    return RouterBackend(ollama=ollama, exo=exo, threshold_gb=settings.exo_threshold_gb)

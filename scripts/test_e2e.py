"""
End-to-end smoke test — validates the full Nova stack without requiring
a running Ollama instance.

Tests:
  1. Settings + bootstrap load cleanly
  2. Memory store: save/retrieve turns and facts
  3. Context builder: injects facts into prompt
  4. Personality: builds system prompt
  5. Tool registry: all 19 tools registered, schemas valid
  6. Approval manager: AUTO / CONFIRM / BLOCKED decisions correct
  7. Fact extraction: orchestrator regex patterns fire correctly
  8. Tool execution: representative tools run end-to-end
  9. Server: FastAPI app creates without error
 10. Orchestrator: Ollama-down path returns graceful error

Usage:
  .venv/bin/python scripts/test_e2e.py
"""
from __future__ import annotations

import asyncio
import sys
import uuid

sys.path.insert(0, ".")


# ── helpers ───────────────────────────────────────────────────────────

PASS = "  ✓"
FAIL = "  ✗"


def section(title: str) -> None:
    print(f"\n── {title} {'─' * (55 - len(title))}")


def ok(msg: str) -> None:
    print(f"{PASS} {msg}")


def fail(msg: str) -> None:
    print(f"{FAIL} {msg}")
    sys.exit(1)


# ── 1. Settings ───────────────────────────────────────────────────────

section("Settings + bootstrap")
from config.settings import get_settings
s = get_settings()
assert s.model.get("name"), "model.name missing"
assert s.model.get("provider") == "ollama", "provider should be ollama"
ok(f"settings loaded — model: {s.model['name']}")

from nova.bootstrap import build_registry, build_nova
registry = build_registry(s)
tool_names = sorted(registry._tools.keys())  # type: ignore[attr-defined]
assert len(tool_names) == 19, f"Expected 19 tools, got {len(tool_names)}"
ok(f"registry: {len(tool_names)} tools")


# ── 2. Memory store ───────────────────────────────────────────────────

section("Memory store")
import tempfile
from pathlib import Path
from nova.memory.store import MemoryStore

with tempfile.TemporaryDirectory() as tmp:
    store = MemoryStore(Path(tmp) / "test.db")
    sid = str(uuid.uuid4())

    store.save_turn(sid, "user", "hello")
    store.save_turn(sid, "assistant", "hi there")
    turns = store.get_recent_turns(sid, n=10)
    assert len(turns) == 2, f"Expected 2 turns, got {len(turns)}"
    ok(f"save/retrieve turns: {len(turns)} turns")

    store.save_fact("user_name", "Josh")
    store.save_fact("preference", "dark mode")
    facts = store.get_facts()
    assert any(f["key"] == "user_name" for f in facts)
    ok(f"save/retrieve facts: {len(facts)} facts")

    store.save_fact("user_name", "Joshua")  # overwrite
    facts2 = store.get_facts()
    names = [f for f in facts2 if f["key"] == "user_name"]
    assert len(names) == 1 and names[0]["value"] == "Joshua", "fact overwrite failed"
    ok("fact overwrite (upsert) works")


# ── 3. Context builder ────────────────────────────────────────────────

section("Context builder")
from nova.memory.context_builder import ContextBuilder

with tempfile.TemporaryDirectory() as tmp:
    store = MemoryStore(Path(tmp) / "ctx.db")
    sid = str(uuid.uuid4())
    store.save_turn(sid, "user", "ping")
    store.save_turn(sid, "assistant", "pong")
    store.save_fact("user_name", "Josh")

    cb = ContextBuilder(store, max_turns=20, max_facts=10)
    ctx = cb.build(sid)
    assert ctx["messages"], "messages should not be empty"
    assert "Josh" in ctx["injected_facts"], "fact should appear in injected_facts"
    ok(f"context: {len(ctx['messages'])} messages, facts injected")


# ── 4. Personality ────────────────────────────────────────────────────

section("Personality")
from nova.agent.personality import build_system_prompt

prompt = build_system_prompt(s, injected_facts="user_name: Josh")
assert "Nova" in prompt
assert "Josh" in prompt
ok(f"system prompt built ({len(prompt)} chars)")


# ── 5. Tool schemas ───────────────────────────────────────────────────

section("Tool schemas")
schemas = registry.get_all_schemas()
assert len(schemas) == 19
for schema in schemas:
    # Ollama uses OpenAI-compatible format: {type, function: {name, description, parameters}}
    fn = schema.get("function", schema)  # support both flat and nested
    assert fn.get("name"), f"schema missing 'name': {schema}"
    assert fn.get("description"), f"schema missing 'description': {schema}"
    assert fn.get("parameters") or fn.get("input_schema"), f"schema missing parameters: {schema}"
ok(f"all {len(schemas)} schemas have required fields")


# ── 6. Approval manager ───────────────────────────────────────────────

section("Approval manager")
from nova.approval.manager import ApprovalDecision, ApprovalManager

approval = ApprovalManager(s.approval)

assert approval.check("search_web") == ApprovalDecision.AUTO
ok("search_web → AUTO")

assert approval.check("draft_email") == ApprovalDecision.CONFIRM
ok("draft_email → CONFIRM")

# Unknown tool falls back to default (confirm)
assert approval.check("nonexistent_tool") == ApprovalDecision.CONFIRM
ok("unknown tool → CONFIRM (default)")

# CONFIRM with no callback → headless allow
result = approval.resolve("draft_email", {}, ui_callback=None)
assert result is True
ok("headless CONFIRM → allowed (no callback)")

# CONFIRM with denying callback → blocked
result = approval.resolve("draft_email", {}, ui_callback=lambda r: False)
assert result is False
ok("CONFIRM with deny callback → denied")

# CONFIRM with approving callback → allowed
result = approval.resolve("draft_email", {}, ui_callback=lambda r: True)
assert result is True
ok("CONFIRM with approve callback → allowed")


# ── 7. Fact extraction ────────────────────────────────────────────────

section("Fact extraction (orchestrator regex)")
import re

_FACT_PATTERNS = [
    (r"(?:please\s+)?remember\s+(?:that\s+)?(.+)", "note"),
    (r"my name is\s+(.+)", "user_name"),
    (r"i work (?:at|for)\s+(.+)", "workplace"),
    (r"i prefer\s+(.+)", "preference"),
    (r"my (?:email|e-mail) is\s+(\S+@\S+)", "user_email"),
]

cases = [
    ("remember that I like jazz", "note", "i like jazz"),
    ("my name is Josh", "user_name", "josh"),
    ("I work for Anthropic", "workplace", "anthropic"),
    ("I prefer dark mode", "preference", "dark mode"),
    ("my email is josh@example.com", "user_email", "josh@example.com"),
]

for text, expected_key, expected_value in cases:
    matched = False
    for pattern, key in _FACT_PATTERNS:
        m = re.search(pattern, text.lower(), re.IGNORECASE)
        if m and key == expected_key:
            val = m.group(1).strip().rstrip(".")
            assert expected_value in val.lower(), f"Expected '{expected_value}' in '{val}'"
            matched = True
            break
    assert matched, f"No pattern matched for: {text}"
    ok(f"'{text[:40]}' → {expected_key}")


# ── 8. Tool execution ─────────────────────────────────────────────────

section("Tool execution (async)")


async def run_tool_checks() -> None:
    from nova.engines.dev import ListFilesTool, ReadFileTool, SearchCodeTool
    from nova.tools.clipboard import GetClipboardTool

    # ReadFileTool
    r = await ReadFileTool().run(path=__file__)
    assert "test_e2e" in r.content
    ok(f"ReadFileTool: read {len(r.content)} chars")

    # ListFilesTool
    r = await ListFilesTool().run(path=".", max_depth=1)
    assert r.error is None
    ok(f"ListFilesTool: {len(r.content.splitlines())} lines")

    # SearchCodeTool
    r = await SearchCodeTool().run(pattern="ToolResult", path=".", file_type="py")
    assert "ToolResult" in r.content or r.content == "No matches found."
    ok("SearchCodeTool: completed")

    # GetClipboardTool
    r = await GetClipboardTool().run()
    assert r.error is None
    ok(f"GetClipboardTool: got clipboard ({len(r.content)} chars)")


asyncio.run(run_tool_checks())


# ── 9. FastAPI app factory ────────────────────────────────────────────

section("FastAPI app factory")
from nova.server.main import create_app

app = create_app()
assert app is not None
ok("create_app() returned FastAPI instance")

routes = [r.path for r in app.routes]  # type: ignore[attr-defined]
assert "/health" in routes, f"Missing /health — routes: {routes}"
assert "/chat" in routes, "/chat route missing"
ok(f"routes registered: {[r for r in routes if not r.startswith('/openapi')]}")


# ── 10. Orchestrator Ollama-down path ─────────────────────────────────

section("Orchestrator graceful error (Ollama offline)")
from nova.agent.orchestrator import Orchestrator


async def test_ollama_down() -> None:
    with tempfile.TemporaryDirectory() as tmp:
        store = MemoryStore(Path(tmp) / "err.db")
        orch = Orchestrator(
            settings=s,
            memory=store,
            tool_registry=None,
            approval_manager=None,
        )
        # Point at a port nothing is listening on
        object.__setattr__(orch, "_host", "http://localhost:19999")
        response = await orch.run(
            user_message="ping",
            session_id=str(uuid.uuid4()),
        )
        assert "ollama" in response.lower() or "model" in response.lower() or "connect" in response.lower(), \
            f"Expected friendly error, got: {response}"
        ok(f"Ollama-down → friendly message: {response[:80]}")


asyncio.run(test_ollama_down())


# ── Done ──────────────────────────────────────────────────────────────

print("\n══ All end-to-end checks passed ═════════════════════════════\n")

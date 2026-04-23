from __future__ import annotations

import asyncio
import re
from collections.abc import Callable
from typing import Any

import ollama

from config.settings import Settings
from nova.agent.personality import build_system_prompt
from nova.approval.manager import ApprovalDecision, ApprovalManager, ApprovalRequest
from nova.memory.context_builder import ContextBuilder
from nova.memory.store import MemoryStore
from nova.services import resource_advisor
from nova.services.location import resolve_weather_location
from nova.services.response_cache import build_llm_cache

_MAX_TOOL_ROUNDS = 8

# Phrases that indicate a search tool returned an error/timeout rather than real results.
# When detected, the orchestrator falls back to answering from the LLM's training data.
_SEARCH_FAILURE_PHRASES = (
    "web search timed out",
    "search unavailable",
    "timed out after",
    "no results found",
    "no credible results found",
    "tool 'search_web' timed out",
    "tool 'search_web' failed",
)


def _is_search_failure(raw: str) -> bool:
    """Return True if *raw* is an error/timeout message rather than real search results."""
    lowered = raw.lower().strip()
    return any(phrase in lowered for phrase in _SEARCH_FAILURE_PHRASES)


def _effective_search_query_message(user_message: str) -> str:
    """
    Strip follow-up wrappers (\"Regarding your previous response: …\") so search
    tools receive the actual question, not kilobytes of quoted chat history.

    Many UIs send one big block (no blank line before the follow-up), so we also
    take everything after the closing double-quote of the embedded reply — otherwise
    the quoted text can falsely match \"rain\" in \"Ukrain…\", search triggers, etc.
    """
    t = (user_message or "").strip()
    if not t.lower().startswith("regarding your previous response"):
        return t

    # Suggestion-click shape: ..."\n\n<short follow-up>  (see page.tsx handleSuggestionClick).
    # Use rfind so an accidental "\n\n inside the quoted block does not win.
    for sep in ('"\n\n', '"\r\n\r\n'):
        p = t.rfind(sep)
        if p != -1:
            after = t[p + len(sep) :].strip()
            if len(after) >= 4:
                return after
    for sep in ('"\n', '"\r\n'):
        p = t.rfind(sep)
        if p != -1 and p > 0:
            after = t[p + len(sep) :].strip()
            if 4 <= len(after) <= 4000 and not after.startswith('"'):
                return after

    blocks = re.split(r"\n\s*\n+", t)
    if len(blocks) >= 2:
        tail = blocks[-1].strip()
        if len(tail) >= 4:
            return tail
    # One paragraph: "…Response: \"…long quote…\" Help me expand" — use text after last "
    if '"' in t:
        lastq = t.rfind('"')
        if lastq > 12 and lastq < len(t) - 1:
            after = t[lastq + 1:].strip().lstrip(": ").strip()
            if len(after) >= 4:
                return after

    # If the quote contained inner \" characters, rfind can leave kilobytes of
    # assistant text in `after` — the real follow-up is usually the last line.
    lines = [ln.strip() for ln in t.splitlines() if ln.strip()]
    if lines:
        last = lines[-1]
        if 4 <= len(last) <= 2000 and not last.lower().startswith("regarding your "):
            return last

    return t


# Tokens that may appear in a pure social / wake turn (no task). Used so the LLM
# router's "default to core" does not override keyword routing to Nova Spark.
_GREET_TRIVIAL: frozenset[str] = frozenset(
    "hey,hi,hello,hiya,heya,howdy,sup,yo,there,mornin,evenin,morning,afternoon,evening,"
    "night,nova,good,thanks,thx,thank,cheers,oh,ok,okay,bye,greetings,greeting,hi,ho".split(
        ","
    )
    + ["'sup"]
)
_GREET_CORE: frozenset[str] = frozenset(
    "hey hi hello hiya heya howdy sup yo morning afternoon evening mornin evenin".split()
)
_GREET_TIME_PAIRS: frozenset[frozenset[str]] = frozenset(
    frozenset(p.split()) for p in ("good morning", "good afternoon", "good evening", "good night")
)


def _is_trivial_social_greeting(clean: str) -> bool:
    """
    True for short wake/social only — e.g. "hey", "hi nova", "hello there", "good morning".
    Excludes any message that is likely a real question or task.
    """
    t = re.sub(r"\[.*?\]", "", clean or "").lower()
    t = re.sub(r"[^a-z0-9''\s-]", " ", t)
    words = [w for w in t.split() if w]
    if not words or len(words) > 4:
        return False
    if not all(w in _GREET_TRIVIAL for w in words):
        return False
    if any(w in _GREET_CORE for w in words):
        return True
    if all(w in ("good",) for w in words) and len(words) == 1:
        return False
    ws = frozenset(words)
    if ws in _GREET_TIME_PAIRS:
        return True
    if "nova" in words and len(words) <= 2:
        return True
    if words in (["hi", "there"], ["hello", "there"], ["hey", "there"]):
        return True
    return False


# Staged writing: Core clarifies when there is no topic; Pro / Creative deliver the piece when there is.
_COMP_TOPIC_ESSAY: list[re.Pattern] = [
    re.compile(
        r"(?:write|create|draft|need|want)\s+(?:an?|the|for me|me an?|me a)\s+"
        r"(?:essay|paper|article|report)(?:\s+for me)?\s*(?:on|about|for|of|regarding)\s+(.+?)(?:[.?!]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\bessay(?:\s+for me)?\s*(?:on|about|for|of|regarding)\s+(.+?)(?:[.?!]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:can you|could you|please)\s+(?:write|create|draft)\s+(?:an?|for me|me an?)\s+"
        r"essay(?:\s+for me)?\s*(?:on|about|for|of|regarding)\s+(.+?)(?:[.?!]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
]
_COMP_TOPIC_CREATIVE: list[re.Pattern] = [
    re.compile(
        r"(?:write|create|draft|need|want)\s+(?:a|an|the|for me|me a)\s+"
        r"(?:short\s+)?story\s*(?:on|about|for)\s+(.+?)(?:[.?!]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"(?:write|create|draft)\s+(?:a|an|the|for me|me a)\s+"
        r"(?:poem|song|lyrics?)\s*(?:on|about|for)\s+(.+?)(?:[.?!]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r"\b(?:story|poem|song|lyrics?)\s+(?:on|about|for)\s+(.+?)(?:[.?!]|$)",
        re.IGNORECASE | re.DOTALL,
    ),
]
_TOPIC_JUNK: frozenset[str] = frozenset(
    "something anything everything nothing help me idk please thanks you it this that".split()
)


def _normalize_composition_topic(raw: str) -> str:
    t = (raw or "").strip().strip("`'\"“”")
    t = re.sub(r"\s+", " ", t)
    if len(t) < 3:
        return ""
    low = t.lower()
    if low in _TOPIC_JUNK or (len(t.split()) == 1 and low in _TOPIC_JUNK):
        return ""
    return t


def _extract_essay_or_creative_topic(clean: str) -> tuple[str, str] | None:
    """
    If the user names a subject for an essay/paper or a story/poem/song, return
    ("essay", topic) or ("creative", topic). Otherwise None.
    """
    for pat in _COMP_TOPIC_ESSAY:
        m = pat.search(clean)
        if m:
            top = _normalize_composition_topic(m.group(1))
            if top:
                return ("essay", top)
    for pat in _COMP_TOPIC_CREATIVE:
        m = pat.search(clean)
        if m:
            top = _normalize_composition_topic(m.group(1))
            if top:
                return ("creative", top)
    return None


def _wants_composition_without_topic(clean: str) -> bool:
    """
    True when the user is asking to write *something* (essay, story, poem, …) but
    there is no extractable subject — use Core to suggest ideas / ask one question.
    """
    if _extract_essay_or_creative_topic(clean):
        return False
    t = (clean or "").lower()
    if re.search(
        r"\b(?:write|draft|create|need|want|help (?:me )?with|can you (?:write|create|draft))\b",
        t,
    ) and re.search(
        r"\b(essay|term paper|article|report|paper|story|poem|song|lyrics?|short story)\b",
        t,
    ):
        return True
    if re.search(r"\bwrite\s+an?\s+essay\b", t) and not re.search(
        r"(?:on|about|for|regarding)\s+[\w\s,'-]{4,}", t
    ):
        return True
    return False


def _format_extracted_fact_value(key: str, raw: str) -> str:
    """Facts are matched on lowercased text; restore readable casing where it matters."""
    if key != "user_display_name":
        return raw
    parts = raw.split()
    if not parts:
        return raw
    return " ".join(p[:1].upper() + p[1:].lower() if p else "" for p in parts)


# Patterns that signal something worth remembering
_FACT_PATTERNS: list[tuple[str, str]] = [
    (r"(?:please\s+)?remember\s+(?:that\s+)?(.+)", "note"),
    # Explicit preferred form of address (takes priority over enrolled full name in context).
    (r"(?:please\s+)?call\s+me\s+([a-z][a-z'\-]+(?:\s+[a-z][a-z'\-]+){0,2})\b", "user_display_name"),
    (r"(?:please\s+)?refer to me as\s+([a-z][a-z'\-]+(?:\s+[a-z][a-z'\-]+){0,2})\b", "user_display_name"),
    (r"(?:please\s+)?address me as\s+([a-z][a-z'\-]+(?:\s+[a-z][a-z'\-]+){0,2})\b", "user_display_name"),
    (r"my name is\s+(.+)", "user_name"),
    (r"i(?:'m| am) called\s+(.+)", "user_name"),
    (r"i work (?:at|for)\s+(.+)", "workplace"),
    (r"i(?:'m| am) (?:a|an)\s+(.+?)(?:\.|$)", "user_role"),
    (r"i live in\s+(.+)", "location"),
    (r"i prefer\s+(.+)", "preference"),
    (r"i(?:'d| would) rather\s+(.+)", "preference"),
    (r"i always\s+(.+)", "habit"),
    (r"my (?:email|e-mail) is\s+(\S+@\S+)", "user_email"),
]


class Orchestrator:
    """
    Central agentic loop — Ollama-powered, fully local, free.

    run() accepts an optional approval_callback: Callable[[ApprovalRequest], bool]
    that is invoked synchronously from the worker thread when a tool requires
    confirmation. Wire the desktop dialog in on Day 4; until then the CLI
    fallback (or headless auto-allow) is used.
    """

    def __init__(
        self,
        settings: Settings,
        memory: MemoryStore,
        tool_registry: Any = None,
        approval_manager: ApprovalManager | None = None,
    ) -> None:
        self._settings = settings
        self._memory = memory
        self._context = ContextBuilder(
            memory,
            max_turns=settings.memory.get("recent_turns_in_context", 20),
            max_facts=settings.memory.get("max_facts_in_context", 10),
        )
        self._registry = tool_registry
        self._approval = approval_manager
        self._location_ctx: str = ""
        self._model         = settings.model.get("name",           "qwen2.5:72b")
        self._fast_model    = settings.model.get("fast_model",     "llama3.2:3b")
        self._swift_model   = settings.model.get("swift_model",    "gemma3:4b")
        self._core_model    = settings.model.get("core_model",     "mistral:7b")
        self._heavy_model   = settings.model.get("heavy_model",    self._model)
        self._code_model    = settings.model.get("code_model",     self._model)
        self._vision_model  = settings.model.get("vision_model",   "llama3.2-vision:11b")
        self._mind_model    = settings.model.get("mind_model",     "gemma3:27b")
        self._creative_model = settings.model.get("creative_model","dolphin-mixtral:8x7b")
        self._insight_model = settings.model.get("insight_model",  "zephyr:7b")
        self._sage_model    = settings.model.get("sage_model",     "nous-hermes:13b")
        self._chat_model    = settings.model.get("chat_model",     "neural-chat:7b")
        self._logic_model   = settings.model.get("logic_model",    "orca-mini:7b")
        self._mini_model    = settings.model.get("mini_model",     "phi:2.7b")
        self._star_model    = settings.model.get("star_model",     "starling-lm:7b")
        self._open_model    = settings.model.get("open_model",     "openchat:7b")
        # ── Quantitative & reasoning specialists ─────────────────────────────
        self._quant_model   = settings.model.get("quant_model",   "mathstral:7b")
        self._reason_model  = settings.model.get("reason_model",  "deepseek-r1:7b")
        self._host = settings.ollama_host
        self._keep_alive = str(settings.model.get("keep_alive", "20m"))
        # Reuse identical (model, messages) completions when safe (see run() gating)
        self._llm_cache = build_llm_cache(settings)

    def set_active_model(self, model_name: str) -> None:
        self._model = model_name

    @property
    def memory(self) -> MemoryStore:
        return self._memory

    def _select_model(self, mode: str, model_key: str | None = None) -> str:
        _key_map = {
            "auto":     self._model,
            "spark":    self._fast_model,
            "basic":    self._fast_model,     # legacy alias
            "air":      self._swift_model,
            "swift":    self._swift_model,    # legacy alias
            "core":     self._core_model,
            "pro":      self._heavy_model,
            "code":     self._code_model,
            "vision":   self._vision_model,
            "mind":     self._mind_model,
            "creative": self._creative_model,
            "insight":  self._insight_model,
            "sage":     self._sage_model,
            "chat":     self._chat_model,
            "logic":    self._logic_model,
            "mini":     self._mini_model,
            "star":     self._star_model,
            "open":     self._open_model,
            # Quantitative & reasoning specialists
            "quant":    self._quant_model,
            "reason":   self._reason_model,
        }
        if model_key and model_key in _key_map:
            return _key_map[model_key]
        if mode == "fast":
            return self._fast_model
        if mode == "code":
            return self._code_model
        return self._model

    def _get_model_name(self, model_id: str) -> str:
        """Map model ID to friendly Nova name."""
        model_map = {
            self._model:         "Nova Pro",
            self._fast_model:    "Nova Spark",
            self._swift_model:   "Nova Air",
            self._core_model:    "Nova Core",
            self._heavy_model:   "Nova Pro",
            self._code_model:    "Nova Code",
            self._vision_model:  "Nova Vision",
            self._mind_model:    "Nova Mind",
            self._creative_model:"Nova Creative",
            self._insight_model: "Nova Insight",
            self._sage_model:    "Nova Sage",
            self._chat_model:    "Nova Chat",
            self._logic_model:   "Nova Logic",
            self._mini_model:    "Nova Mini",
            self._star_model:    "Nova Star",
            self._open_model:    "Nova Open",
            self._quant_model:   "Nova Quant",
            self._reason_model:  "Nova Reason",
        }
        return model_map.get(model_id, "Nova")

    # ── Auto-routing signal tables ────────────────────────────────────────────
    # Each entry is (keyword, score).  Scores accumulate; highest category wins.
    # Use higher scores for strong/unambiguous signals, lower for weak ones.

    _CODE_SIGNALS: list[tuple[str, int]] = [
        # Programming languages (very strong signal — 3pts each)
        *[(lang, 3) for lang in (
            "python", "javascript", "typescript", "java", "kotlin", "swift",
            "c++", "c#", "golang", "go lang", "rust", "ruby", "php", "bash",
            "shell script", "html", "css", "react", "vue", "angular", "django",
            "spring boot", "flutter", "android", "ios app", "node.js", "nodejs",
        )],
        # Coding action words (2pts)
        *[(w, 2) for w in (
            "write a program", "write me a program", "write a script",
            "write a function", "write a class", "implement", "refactor",
            "debug", "fix this code", "fix the bug", "fix this error",
            "unit test", "write tests", "stack trace", "traceback",
            "compile error", "syntax error", "runtime error",
        )],
        # Weaker code signals (1pt — only decisive when combined)
        *[(w, 1) for w in (
            "code", "program", "function", "class", "algorithm",
            "data structure", "linked list", "binary tree", "sql", "regex",
            "api", "rest api", "graphql", "crud", "snake game", "tic tac toe",
            "chess game", "calculator", "todo app", "build a", "create a",
        )],
    ]

    _HEAVY_SIGNALS: list[tuple[str, int]] = [
        # Strong composition (4pts) — must hit Nova Pro threshold without relying on the JSON router
        *[(w, 4) for w in (
            "write an essay", "write me an essay", "write the essay", "essay for me",
            "write a paper", "term paper", "write an article", "write a report",
        )],
        # Deep analytical intent (3pts)
        *[(w, 3) for w in (
            "analyze in depth", "detailed analysis", "thorough analysis",
            "compare and contrast", "pros and cons", "trade-offs", "tradeoffs",
            "long-form", "comprehensive", "exhaustive", "step by step",
            "explain everything", "full breakdown", "deep dive",
            "research paper", "essay", "dissertation", "thesis",
        )],
        # Research / strategic thinking (2pts)
        *[(w, 2) for w in (
            "analyze", "analysis", "evaluate", "assessment", "review",
            "strategy", "roadmap", "architecture", "design pattern",
            "what are the implications", "what would happen if",
            "explain why", "explain how", "compare", "difference between",
            "pros and cons", "decision", "should i", "recommend",
            "best approach", "best practice",
        )],
        # Math / logic (2pts)
        *[(w, 2) for w in (
            "calculate", "compute", "solve", "equation", "formula",
            "proof", "derive", "statistics", "probability", "integral",
            "derivative", "linear algebra", "matrix", "theorem",
        )],
        # Length/complexity hints (1pt)
        *[(w, 1) for w in (
            "explain", "describe", "elaborate", "detail", "breakdown",
            "overview", "summarize at length", "tell me about",
        )],
    ]

    _QUICK_SIGNALS: list[tuple[str, int]] = [
        # Explicit speed requests (3pts)
        *[(w, 3) for w in (
            "quick answer", "short answer", "one line", "one sentence",
            "briefly", "in a word", "tldr", "just tell me", "just say",
        )],
        # Simple factual lookups (2pts)
        *[(w, 2) for w in (
            "what time", "what day", "what date", "what year",
            "how do you spell", "definition of", "what does",
            "convert", "translate this word",
        )],
    ]

    _CREATIVE_SIGNALS: list[tuple[str, int]] = [
        *[(w, 3) for w in (
            "write a story", "write a poem", "write a song", "write lyrics",
            "write a script", "creative writing", "fiction", "short story",
            "write a joke", "write a rap",
        )],
        *[(w, 2) for w in (
            "brainstorm", "come up with ideas", "creative", "imaginative",
            "tagline", "marketing copy", "brand voice", "slogan",
            "caption", "narrative", "plot", "character",
        )],
        *[(w, 1) for w in (
            "story", "poem", "script", "creative", "imagine",
        )],
    ]

    # ── Generation requests (image / document / music / chart / diagram) → Nova Core
    # These requests fire a side-car generation event; the LLM writes the full content
    # or confirmation while the side-car handles the actual file/media generation.
    _GENERATION_SIGNALS: list[tuple[str, int]] = [
        # Image / drawing / sketch / art style generation (strong — 4pts)
        *[(w, 4) for w in (
            "generate an image", "generate image", "generate a random image",
            "generate me an image", "create an image", "create image",
            "draw me", "draw a", "draw an", "paint me", "paint a",
            "generate a picture", "create a picture", "make a picture",
            "make an image", "make me an image", "make me a picture",
            "generate a photo", "create a photo", "illustrate",
            "stable diffusion", "text to image", "text-to-image",
            "imagine a", "imagine an",
            "generate a poster", "design a logo", "generate art", "create art",
            "make art", "render an image",
            # Note: "show me an image" is web-browse, not text-to-image — see chat._is_web_image_browse_request
            # Artistic styles — always generation
            "pencil sketch", "sketch of", "draw as a sketch", "watercolor of",
            "oil painting of", "pixel art of", "vector art of", "anime art",
            "cartoon style", "charcoal drawing",
        )],
        # Document generation (strong — 4pts)
        *[(w, 4) for w in (
            "word document", "docx", "excel spreadsheet", "xlsx", "spreadsheet",
            "pdf document", "generate a pdf", "create a pdf", "export as pdf",
            "powerpoint", "pptx", "presentation slides", "slide deck",
            "make a presentation", "create a presentation", "generate a presentation",
            "make slides", "create slides",
            "create a document", "make a document", "write a document",
            "create a report", "make a report", "generate a report",
            "text file", "csv file", "comma separated",
        )],
        # Music / beat generation (strong — 4pts)
        *[(w, 4) for w in (
            "generate a beat", "make a beat", "create a beat",
            "generate music", "make music", "create music",
            "generate a track", "make a track", "create a track",
            "generate piano", "create piano", "make piano",
            "generate some music", "make some music",
            "lo-fi beat", "hip hop beat", "produce a beat", "compose music",
        )],
        # Diagram / flowchart generation (strong — 4pts)
        *[(w, 4) for w in (
            "flowchart", "flow chart", "flow diagram",
            "sequence diagram", "er diagram", "entity relationship diagram",
            "class diagram", "state diagram", "architecture diagram",
            "mind map", "create a diagram", "make a diagram", "draw a diagram",
            "generate a diagram", "draw a flowchart", "create a flowchart",
        )],
    ]

    # ── Chart / data visualization signals → Nova Insight (analytical + chart JSON)
    _CHART_SIGNALS: list[tuple[str, int]] = [
        *[(w, 4) for w in (
            "bar chart", "pie chart", "line chart", "line graph", "area chart",
            "scatter plot", "scatter chart", "scatter graph",
            "data visualization", "data visualisation",
            "generate a chart", "create a chart", "make a chart",
            "generate a graph", "create a graph", "make a graph",
            "plot this", "plot the data", "chart this", "graph this",
            "visualize the data", "visualise the data",
            "show me a chart", "show me a graph",
        )],
        *[(w, 2) for w in (
            "chart", "graph", "plot", "histogram", "diagram chart",
            "visualize", "visualise", "statistics chart",
        )],
    ]

    # ── Quantitative mathematics / computation → Nova Quant ──────────────────
    # Triggers when the query contains dense mathematical vocabulary.
    # Threshold: ≥ 5 points so accidental uses of single terms don't mis-route.
    _QUANT_SIGNALS: list[tuple[str, int]] = [
        # High-specificity math topics (4 pts each — very strong signal)
        *[(w, 4) for w in (
            "eigenvalue", "eigenvector", "linear algebra", "matrix inversion",
            "singular value decomposition", "svd", "gradient descent",
            "lagrange multiplier", "fourier transform", "laplace transform",
            "z-transform", "numerical methods", "numerical analysis",
            "differential equation", "ordinary differential equation",
            "partial differential equation", "integration by parts",
            "taylor series", "maclaurin series", "l'hopital",
            "standard deviation", "variance", "hypothesis test", "p-value",
            "confidence interval", "t-test", "chi-square", "anova", "f-test",
            "regression analysis", "linear regression", "logistic regression",
            "bayes theorem", "bayesian", "markov chain", "monte carlo simulation",
            "sharpe ratio", "beta coefficient", "volatility", "value at risk", "var",
            "net present value", "npv", "internal rate of return", "irr",
            "discounted cash flow", "dcf", "black-scholes", "option pricing",
            "binomial model", "stochastic", "brownian motion",
            "maximum likelihood estimation", "mle", "least squares",
            "principal component analysis", "pca", "clustering algorithm",
            "gradient", "hessian", "jacobian", "lagrangian",
        )],
        # Moderate math signals (2 pts each)
        *[(w, 2) for w in (
            "integral", "integrate", "differentiate", "derivative",
            "probability distribution", "statistics", "statistical analysis",
            "portfolio", "annualized return", "compounding", "amortization",
            "standard error", "correlation coefficient", "covariance matrix",
            "factorial", "permutation", "combination", "binomial distribution",
            "poisson distribution", "normal distribution", "gaussian",
            "percentile", "quartile", "interquartile range",
            "expected value", "variance reduction", "central limit theorem",
            "modular arithmetic", "number theory", "prime factorization",
        )],
        # Weak math signals (1 pt — decisive only in combination)
        *[(w, 1) for w in (
            "probability", "statistics", "calculate", "compute",
            "formula", "equation", "matrix", "vector",
            "integral", "derivative", "calculus", "algebra",
        )],
    ]

    # ── Deep reasoning / proofs / derivations → Nova Reason ──────────────────
    # Chain-of-thought model; triggers on explicit proof/derivation intent.
    # Threshold: ≥ 4 points (one strong proof term is enough).
    _REASON_SIGNALS: list[tuple[str, int]] = [
        # Strong proof / derivation signals (4 pts each)
        *[(w, 4) for w in (
            "prove that", "mathematical proof", "formal proof",
            "derive the formula", "derive an expression",
            "derive from first principles", "from first principles",
            "proof by induction", "proof by contradiction",
            "proof by contrapositive", "induction hypothesis",
            "show that it follows", "rigorously show",
            "theorem", "lemma", "corollary", "conjecture",
            "axiom", "formal logic", "predicate logic", "propositional logic",
            "verify that", "demonstrate that", "rigorously derive",
        )],
        # Step-by-step reasoning signals (2 pts each)
        *[(w, 2) for w in (
            "step by step", "step-by-step", "show your work",
            "show the steps", "walk me through", "think through",
            "reason through", "chain of thought", "logical reasoning",
            "systematically solve", "break down the steps",
            "how do we know that", "why is it true",
            "formal reasoning", "rigorous explanation",
        )],
        # Weak reasoning signals (1 pt)
        *[(w, 1) for w in (
            "prove", "proof", "derive", "deduce", "infer",
            "theorem", "logical", "reasoning", "systematic",
        )],
    ]

    # Conversational / personal questions → Nova Core (balanced, tool-capable)
    _CHAT_SIGNALS: list[tuple[str, int]] = [
        *[(w, 3) for w in (
            "life advice", "advice for", "what should i do", "how do i deal",
            "how are you", "how's it going", "what do you think about",
            "your opinion", "do you think", "talk to me", "chat with me",
            "tell me something", "cheer me up", "motivate me",
            "i'm feeling", "i feel", "feeling sad", "feeling lost",
            "relationship advice", "career advice", "personal advice",
        )],
        *[(w, 2) for w in (
            "advice", "opinion", "thoughts on", "what do you think",
            "suggest", "recommendation", "suggest something",
            "fun fact", "did you know", "tell me about yourself",
            "what's your favorite", "do you like", "have you ever",
            "jokes", "funny", "make me laugh",
        )],
        *[(w, 1) for w in (
            "hey", "hi", "hello", "thanks", "thank you", "cool", "nice",
            "interesting", "wow", "really", "seriously",
        )],
    ]

    def _auto_select_model(self, user_message: str) -> tuple[str, str]:
        """
        Score the request across categories and route to the best model.

        Routing priority (highest to lowest):
          code (≥2)  → Nova Code     — dedicated coding specialist
          heavy (≥4) → Nova Pro      — deep research & reasoning only when justified
          creative   → Nova Creative — writing, brainstorming, style
          chat       → Nova Core     — conversational, personal, opinions
          quick      → Nova Spark    — ultra-short factual one-liners
          general    → Nova Core     — balanced fallback (tool-capable)
        """
        text = (user_message or "").lower()
        word_count = len(text.split())

        # ── Score each category ──────────────────────────────────────────────
        scores: dict[str, int] = {
            "code": 0, "heavy": 0, "quick": 0, "creative": 0,
            "chat": 0, "generation": 0, "chart": 0,
            "quant": 0, "reason": 0,
        }

        for keyword, pts in self._CODE_SIGNALS:
            if keyword in text:
                scores["code"] += pts

        for keyword, pts in self._HEAVY_SIGNALS:
            if keyword in text:
                scores["heavy"] += pts

        for keyword, pts in self._QUICK_SIGNALS:
            if keyword in text:
                scores["quick"] += pts

        for keyword, pts in self._CREATIVE_SIGNALS:
            if keyword in text:
                scores["creative"] += pts

        for keyword, pts in self._CHAT_SIGNALS:
            if keyword in text:
                scores["chat"] += pts

        for keyword, pts in self._GENERATION_SIGNALS:
            if keyword in text:
                scores["generation"] += pts

        for keyword, pts in self._CHART_SIGNALS:
            if keyword in text:
                scores["chart"] += pts

        for keyword, pts in self._QUANT_SIGNALS:
            if keyword in text:
                scores["quant"] += pts

        for keyword, pts in self._REASON_SIGNALS:
            if keyword in text:
                scores["reason"] += pts

        # ── Length-based complexity boost ────────────────────────────────────
        # Long, detailed questions deserve more capable models.
        if word_count >= 60:
            scores["heavy"] += 3
        elif word_count >= 30:
            scores["heavy"] += 1

        # Very short messages are likely quick one-liners.
        if word_count <= 5:
            scores["quick"] += 3
        elif word_count <= 8:
            scores["quick"] += 1

        # ── Pick winner ──────────────────────────────────────────────────────
        best_score = max(scores.values())

        # Generation requests (image / doc / music / diagram) → Nova Core.
        # Side-car generation service handles the actual file; LLM writes content/confirmation.
        if scores["generation"] >= 4:
            return self._core_model, "generation"

        # Chart / data visualization → Nova Insight (analytical, structured output for chart JSON)
        if scores["chart"] >= 4:
            return self._insight_model, "chart"

        # Code always routes to the specialist, regardless of ties.
        if scores["code"] >= 2:
            return self._code_model, "code"

        # Quantitative math → Nova Quant (dedicated math model, near-zero temperature)
        # Threshold ≥ 5 prevents false triggers from single weak math terms.
        if scores["quant"] >= 5:
            return self._quant_model, "quant"

        # Proof / derivation / CoT reasoning → Nova Reason (deepseek-r1 chain-of-thought)
        # One strong proof keyword (4 pts) is enough to warrant the specialist.
        if scores["reason"] >= 4:
            return self._reason_model, "reason"

        # If the query scores equally for quant/heavy, prefer Quant for math topics.
        if scores["quant"] >= 3 and scores["quant"] >= scores["heavy"]:
            return self._quant_model, "quant"

        # Nova Pro activates for any substantive query — quality over speed.
        # Threshold ≥ 3 so "essay", "analyze", "explain in depth" all go Pro.
        if scores["heavy"] >= 3:
            return self._heavy_model, "reasoning"

        if scores["creative"] == best_score and scores["creative"] >= 2:
            return self._creative_model, "creative"

        # Conversational / personal → Nova Core (fast, tool-capable, balanced)
        if scores["chat"] == best_score and scores["chat"] >= 2:
            return self._core_model, "chat"

        # Ultra-short factual one-liners → Nova Spark
        if scores["quick"] >= 3:
            return self._fast_model, "quick"

        # General fallback — Nova Core handles most everyday queries well.
        return self._core_model, "general"

    # ── LLM-based router ─────────────────────────────────────────────────────

    _ROUTER_PROMPT = """You are a routing assistant for Nova AI. Your priority is quality and accuracy. When in doubt, pick the most capable model.

Available models:
- spark   : Greetings only — "hi", "hey nova", tiny yes/no with no real question (under 5 words)
- air     : Casual small-talk, simple chitchat — no information or task needed
- core    : Tool-requiring tasks: news, weather, web search, current events, AND all media generation requests (image, music, charts, documents)
- pro     : Any substantive question, explanation, advice, analysis, research, summaries, named-topic essays, articles, reports — DEFAULT for anything non-trivial
- code    : Any coding, programming, debugging, scripts, algorithms, or technical implementation
- creative: Fiction stories, poems, song lyrics, rap, creative writing, marketing copy — NOT essays or factual reports
- insight : Data analysis, statistics, charts with explanation, numbers, structured comparisons
- sage    : Strict formatting, tables, bullet reports, structured output, precise instructions
- vision  : Understanding/describing an image the user has ALREADY shared
- quant   : Pure maths — calculus, algebra, probability, financial modelling, integrals, eigenvalues
- reason  : Formal proofs, theorems, derivations, step-by-step logical reasoning

Routing priority (QUALITY FIRST):
1. CODE → "code" always — never "core" for programming
2. MATH COMPUTATION → "quant" — equations, statistics, financial modelling
3. FORMAL PROOF / DERIVATION → "reason"
4. Named-topic ESSAY / ARTICLE / REPORT (on, about, of, regarding a specific subject) → "pro"
5. Named STORY / POEM / LYRICS → "creative"
6. IMAGE / DRAWING / SKETCH generation → "core" (media pipeline handles it)
7. CHART / GRAPH → "insight"
8. MUSIC / DOCUMENT / DIAGRAM generation → "core"
9. Any question requiring tools (news, weather, web) → "core"
10. Pure greeting ("hi", "hey", "hello" with no question/task) → "spark"
11. Everything else substantive — explanation, advice, research, "what is", "how does", "tell me about", "why", "describe", "compare" — → "pro"

IMPORTANT: Use "pro" liberally for any non-trivial question. Only use "core" for tool-requiring tasks or media generation. Only use "spark"/"air" for pure social greetings.
Default to "pro" when unsure. Never use "vision" for generating new images.

Respond ONLY with valid JSON, no other text:
{"model": "<key>", "reason": "<3-5 word reason>"}"""

    async def _llm_route(self, user_message: str) -> tuple[str, str] | None:
        """
        Use a small, reliable model (Ollama chat) to classify the query and pick the best model.
        Returns (model_id, category_label) or None if routing fails / times out.
        Trivial social greetings are overridden in run() to match keyword "quick" (Spark) when the router says "core".
        """
        import json as _json

        import httpx

        messages = [
            {"role": "system", "content": self._ROUTER_PROMPT},
            {"role": "user", "content": user_message[:600]},
        ]
        try:
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.post(
                    f"{self._host}/api/chat",
                    json={
                        "model": self._core_model,  # Nova Core (mistral:7b) — best JSON reliability & intent accuracy for routing
                        "messages": messages,
                        "stream": False,
                        "options": {"num_predict": 60, "temperature": 0.1},
                    },
                )
                resp.raise_for_status()
                content = resp.json()["message"]["content"].strip()

            # Extract JSON even if the model adds surrounding text
            m = re.search(r'\{[^}]+\}', content, re.DOTALL)
            if not m:
                return None
            data = _json.loads(m.group())
            model_key = str(data.get("model", "core")).strip().lower()
            reason = str(data.get("reason", "llm-routed")).strip()

            resolved = self._select_model("default", model_key)
            return resolved, reason

        except Exception:
            return None  # silently fall through to keyword scoring

    # ── Tool-Augmented Generation (TAG) ──────────────────────────────────────

    _TAG_INTEGRATOR_PROMPT = """\
You are an integrator. You receive two inputs:
1. A base response generated by a capable language model from its training knowledge.
2. Live data retrieved by a tool-capable agent (web search, weather, news, etc.).

Your job:
- If the live data is RELEVANT to the question, enrich the base response with it naturally.
- If the live data adds nothing new or contradicts the question's intent, discard it and return the base response refined.
- Never mention "base response", "tool agent", "live data", or any internal pipeline detail.
- Produce a single seamless, high-quality final answer as if you knew everything from the start.
- Keep the tone and style of the base response."""

    async def _tool_augmented_run(
        self,
        user_message: str,
        messages: list[dict],
        tools: list,
        system_text: str,
        stream_callback: Callable[[str], None] | None,
        status_callback: Callable[[str], None] | None,
        primary_model: str,
    ) -> str:
        """
        Parallel pipeline:
          - primary_model   → generates a base response (no tools, runs from training knowledge)
          - tool_agent      → Nova Core (mistral:7b) fetches live data via tools
          Both run concurrently; an integrator then merges the results intelligently.
        """
        import httpx as _httpx

        tool_model = self._core_model  # lightest tool-capable model

        # ── 1. Run primary model (plain, no tools) ────────────────────────────
        async def _run_primary() -> str:
            try:
                async with _httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{self._host}/api/chat",
                        json={
                            "model": primary_model,
                            "messages": messages,
                            "stream": False,
                            "options": {"num_predict": 1024, "temperature": 0.7},
                        },
                    )
                    resp.raise_for_status()
                    return resp.json()["message"]["content"].strip()
            except Exception:
                return ""

        # ── 2. Run tool agent (mistral:7b with tools, no streaming needed) ────
        async def _run_tool_agent() -> str:
            try:
                tool_schemas = tools if tools else []
                if not tool_schemas:
                    return ""
                async with _httpx.AsyncClient(timeout=30.0) as client:
                    resp = await client.post(
                        f"{self._host}/api/chat",
                        json={
                            "model": tool_model,
                            "messages": messages,
                            "tools": tool_schemas,
                            "stream": False,
                            "options": {"num_predict": 512, "temperature": 0.2},
                        },
                    )
                    resp.raise_for_status()
                    data = resp.json()
                    content = data.get("message", {}).get("content", "").strip()
                    # If the tool agent made tool calls, execute them and collect results
                    tool_calls = data.get("message", {}).get("tool_calls", [])
                    if tool_calls and self._registry:
                        results = []
                        for tc in tool_calls:
                            fn = tc.get("function", {})
                            name = fn.get("name", "")
                            args = fn.get("arguments", {})
                            tool = self._registry.get(name)
                            if tool:
                                try:
                                    result = tool.run(**args) if not asyncio.iscoroutinefunction(tool.run) else await tool.run(**args)
                                    results.append(f"[{name}]: {result}")
                                except Exception as e:
                                    results.append(f"[{name} error]: {e}")
                        return "\n".join(results) if results else content
                    return content
            except Exception:
                return ""

        # ── 3. Run both in parallel ───────────────────────────────────────────
        self._emit_status(status_callback, "Running parallel analysis…")
        primary_response, live_data = await asyncio.gather(_run_primary(), _run_tool_agent())

        if not primary_response:
            return ""

        # If tool agent produced nothing useful, stream the primary response directly
        if not live_data or live_data.strip() == primary_response.strip():
            if stream_callback:
                stream_callback(primary_response)
            return primary_response

        # ── 4. Integrate: merge primary response + live data ──────────────────
        self._emit_status(status_callback, "Integrating live data with response…")
        integration_messages = [
            {"role": "system", "content": self._TAG_INTEGRATOR_PROMPT},
            {
                "role": "user",
                "content": (
                    f"Original question: {user_message}\n\n"
                    f"Base response:\n{primary_response}\n\n"
                    f"Live data retrieved:\n{live_data}\n\n"
                    "Produce the final integrated answer."
                ),
            },
        ]
        try:
            import ollama as _ollama
            client = _ollama.Client(host=self._host)
            opts = self._build_options(tool_model)
            return self._stream_text(client, integration_messages, stream_callback, status_callback, tool_model, opts)
        except Exception:
            # Integration failed — fall back to primary
            if stream_callback:
                stream_callback(primary_response)
            return primary_response

    async def run(
        self,
        user_message: str,
        session_id: str,
        stream_callback: Callable[[str], None] | None = None,
        status_callback: Callable[[str], None] | None = None,
        approval_callback: Callable[[ApprovalRequest], bool] | None = None,
        mode: str = "default",  # "default" | "fast" | "code"
        model_key: str | None = None,
        display_message: str | None = None,
    ) -> str:
        # display_message: clean human-readable text stored in memory & facts.
        # user_message: full context (may include system tags) sent only to the LLM.
        mem_message = display_message if display_message is not None else user_message

        direct_memory_response = self._execute_memory_request_route(user_message, status_callback)
        if direct_memory_response is not None:
            if stream_callback and direct_memory_response:
                stream_callback(direct_memory_response)
            self._memory.save_turn(session_id, "user", mem_message)
            self._memory.save_turn(session_id, "assistant", direct_memory_response)
            self._maybe_extract_facts(mem_message)
            return direct_memory_response

        # ── Compute clean message early — needed for both routing and search ────
        _clean_msg = re.sub(r"\[.*?\]", "", user_message).strip()
        _search_msg = _effective_search_query_message(user_message)

        # Determine routing mode early so we can launch routing in parallel with search.
        _is_code = mode == "code" or model_key == "code"
        _use_auto = (
            model_key in (None, "", "auto", "default")
            and not _is_code
        ) or (
            mode == "fast"
            and model_key not in ("code", "pro", "insight", "creative", "sage")
            and self._auto_select_model(_clean_msg)[1] == "code"
        )

        # ── Launch search + routing in parallel ──────────────────────────────────
        # Both tasks fire immediately; we collect their results after a shared
        # 5-second window.  This means the routing LLM call "costs" nothing extra
        # in wall-clock time — it completes while the search is already in flight.
        _search_context: str = ""
        _search_task:   asyncio.Task[str | None]              | None = None
        _route_task:    asyncio.Task[tuple[str, str] | None]  | None = None
        _llm_route_result: tuple[str, str] | None = None

        # Only *_search_msg* (effective question) for intent — never the full `user_message`
        # with quoted history, or \"rain\" substrings in \"Ukrain…\" and similar fire tools.
        _needs_search = (
            self._registry
            and not self._is_memory_request(user_message)
            and not self._is_local_vision_question(user_message)
            and (
                self._is_news_request(_search_msg)
                or self._is_weather_request(_search_msg)
                or self._is_online_search_request(_search_msg)
                or self._is_live_info_request(_search_msg)
                or self._factual_lookup_intent(_search_msg)
                or self._needs_web_search(_search_msg)
            )
        )

        if _needs_search:
            self._emit_status(status_callback, "Live lookup mode enabled")
            self._emit_status(status_callback, "Searching online")
            _search_task = asyncio.create_task(
                self._fetch_search_context_async(user_message, _search_msg)
            )

        # Fire LLM routing in parallel (no-op if not auto-routing)
        if _use_auto:
            _route_task = asyncio.create_task(self._llm_route(_clean_msg))

        # Race: wait for search results (slightly generous — Brave/DDG + long contexts)
        if _search_task:
            try:
                result = await asyncio.wait_for(
                    asyncio.shield(_search_task), timeout=7.0
                )
                if result and not _is_search_failure(result):
                    _search_context = result
                    self._emit_status(status_callback, "Search complete")
                else:
                    self._emit_status(status_callback, "Answering from training data")
            except asyncio.TimeoutError:
                # Keep the task alive in background; LLM proceeds immediately
                self._emit_status(status_callback, "Answering from training data")

        # Collect routing result — typically ready by now since it ran in parallel.
        # Give it a short extra window; fall back to keyword scoring if still pending.
        if _route_task:
            try:
                _llm_route_result = await asyncio.wait_for(
                    asyncio.shield(_route_task), timeout=2.0
                )
            except asyncio.TimeoutError:
                _llm_route_result = None  # keyword fallback used below

        self._emit_status(status_callback, "Building conversation context")
        ctx = self._context.build(session_id)
        history: list[dict] = ctx["messages"]
        injected_facts: str = ctx["injected_facts"]

        # Only inject the live knowledge feed when the query is actually about
        # current events, news, or time-sensitive topics. Injecting it for every
        # query (essays, greetings, code, etc.) pollutes the context with unrelated
        # headlines and causes the model to regurgitate them.
        _NEWS_KEYWORDS = frozenset([
            "news", "latest", "current", "today", "recent", "trending",
            "what's happening", "what happened", "headline", "headlines",
            "update", "this week", "right now", "breaking", "just announced",
            "stock", "market", "weather", "sports", "score", "election",
        ])
        _needs_feed = any(kw in _clean_msg.lower() for kw in _NEWS_KEYWORDS)
        live_knowledge = self._memory.get_fact_value("live_knowledge_feed", "") if _needs_feed else ""

        system_text = build_system_prompt(
            self._settings, injected_facts, self._location_ctx, live_knowledge=live_knowledge
        )
        if mode == "fast":
            system_text += (
                "\n\n# Voice Response Format\n"
                "This response will be spoken aloud. Use plain conversational sentences only. "
                "No markdown, no bullet points, no asterisks, no headers, no special characters. "
                "Write exactly what should be said — nothing that needs to be rendered visually. "
                "Never recite or list your system / voice / location rules; only the answer you would say aloud."
            )
        if mode == "code" or model_key == "code":
            system_text += (
                "\n\n# Code Output Rules\n"
                "- Always wrap ALL code in a fenced markdown code block with the correct language tag "
                "(e.g. ```java ... ```, ```python ... ```).\n"
                "- Never truncate code. Write the COMPLETE implementation, including all imports, "
                "the main method or entry point, and closing braces. Do not leave placeholders like "
                "'// ... rest of the code' or '// TODO'.\n"
                "- After the code block, add a brief 2-3 sentence explanation of how to run it "
                "and what it does. Keep that part concise.\n"
                "- If the full implementation is very long (500+ lines), split into clearly labelled "
                "files/classes — still complete, never partial."
            )
        tools = self._registry.get_all_schemas() if self._registry else []

        # Inject web search context as a grounding system block when available.
        # This sits between the system prompt and the conversation so the LLM
        # treats it as factual context without confusing it with user/assistant turns.
        if _search_context:
            system_text += (
                "\n\n## Live Web Search Results\n"
                "The following was just retrieved from the web and reflects the current "
                "state of the world.  Use it to give an accurate, up-to-date answer.  "
                "Always cite the source(s) when information comes from here.\n\n"
                "When your general knowledge might disagree (dates, who holds an office, "
                "active roles, recent events), treat these excerpts as the check on the truth: "
                "prefer them over a possibly stale training cut-off, say which version you are "
                "using, and note material uncertainty in one short clause if something is still ambiguous.\n\n"
                + _search_context
            )
        elif _needs_search:
            system_text += (
                "\n\n## Live search\n"
                "A web lookup was started for this question but no excerpts arrived in time "
                "or the provider returned nothing usable. Answer from your best knowledge; "
                "for albums, singles, and chart positions, give your most likely answer and "
                "era. Do not instruct the user to open a browser or \"run a web search\" — "
                "they already requested live lookup here."
            )

        messages: list[dict] = (
            [{"role": "system", "content": system_text}]
            + history
            + [{"role": "user", "content": user_message}]
        )

        # ── Model selection ───────────────────────────────────────────────────────
        # _is_code / _use_auto already computed above alongside the parallel tasks.
        if _is_code:
            selected_model = self._code_model
            signal_category = "code"
            model_name = self._get_model_name(selected_model)
            self._emit_status(status_callback, f"Using {model_name} (code)")
        elif _use_auto:
            self._emit_status(status_callback, "Routing to best model…")
            # Use routing result collected in parallel; fall back to keyword scoring
            if _llm_route_result:
                selected_model, signal_category = _llm_route_result
                # The JSON router often defaults to "core" for short openers; keyword
                # scoring routes them to Spark (quick). Prefer Spark so the model does
                # not "document" the long system prompt on a simple hi/hey.
                if _is_trivial_social_greeting(_clean_msg):
                    km, kc = self._auto_select_model(_clean_msg)
                    if kc == "quick":
                        selected_model, signal_category = km, kc
                model_name = self._get_model_name(selected_model)
                self_routed = selected_model == self._core_model
                label = f"{model_name} (self-routed)" if self_routed else f"{model_name} ({signal_category})"
                self._emit_status(status_callback, f"Auto-selected {label}")
            else:
                # Fallback: keyword scoring (instant, no extra LLM call)
                selected_model, signal_category = self._auto_select_model(_clean_msg)
                model_name = self._get_model_name(selected_model)
                self._emit_status(status_callback, f"Auto-selected {model_name} ({signal_category}, keyword)")

            # Staged long-form: vague topic → Core; named essay → Pro; named story/poem/song → Creative
            _prev_m = (selected_model, signal_category)
            if _wants_composition_without_topic(_clean_msg):
                selected_model, signal_category = self._core_model, "composition_clarify"
            else:
                _spec = _extract_essay_or_creative_topic(_clean_msg)
                if _spec is not None:
                    if _spec[0] == "essay":
                        selected_model, signal_category = self._heavy_model, "staged_essay"
                    else:
                        selected_model, signal_category = self._creative_model, "staged_creative"
            if (selected_model, signal_category) != _prev_m:
                model_name = self._get_model_name(selected_model)
                self._emit_status(
                    status_callback,
                    f"Staged long-form: {model_name} ({signal_category})",
                )
        else:
            selected_model = self._select_model(mode, model_key)
            model_name = self._get_model_name(selected_model)
            self._emit_status(status_callback, f"Using {model_name}")

        # ── Middle-ground tool adjuster ───────────────────────────────────────
        # Evaluate whether this specific query actually needs live tools.
        # If it does and the selected model can't handle tools, upgrade to the
        # lightest tool-capable model (Nova Core). Only go to Nova Pro if the
        # query also has heavy/complex signals. If the query doesn't need tools,
        # skip the tool list entirely regardless of model capability.
        _TOOL_NEED_KEYWORDS = frozenset([
            "weather", "forecast", "temperature", "rain", "sunny",
            "news", "headline", "headlines", "latest", "trending", "breaking",
            "search", "look up", "find out", "google", "web",
            "stock", "price", "market", "bitcoin", "crypto",
            "score", "game", "match", "standings",
            "current", "right now", "today's", "this week",
        ])
        _HEAVY_TOOL_KEYWORDS = frozenset([
            "research", "analyze", "summarize multiple", "compare sources",
            "deep dive", "full report", "comprehensive",
        ])
        _TOOL_CAPABLE_MODELS = {self._core_model, self._heavy_model, self._code_model, self._vision_model}

        def _model_can_use_tools(m: str) -> bool:
            _ALLOWLIST = ("qwen2.5", "mistral:", "llama3.2", "llama3.1", "llama3.3")
            return any(p in m.lower() for p in _ALLOWLIST) and m != self._fast_model

        _query_lower = _clean_msg.lower()
        _query_wants_tools = any(kw in _query_lower for kw in _TOOL_NEED_KEYWORDS)
        _query_is_heavy = any(kw in _query_lower for kw in _HEAVY_TOOL_KEYWORDS)

        if not _query_wants_tools:
            # Query doesn't need live tools — skip them entirely for speed
            tools = []

        # ── Tool-Augmented Generation: activate when selected model can't use tools
        # but the query benefits from live data.  Run primary + tool agent in
        # parallel, then integrate the best of both worlds.
        _use_tag = (
            _query_wants_tools
            and tools
            and not _model_can_use_tools(selected_model)
        )

        # Safe to reuse a prior Ollama output only when the prompt is identical and
        # we did not add live-internet or time-varying system blocks.
        _llm_cache_ok = (
            self._llm_cache is not None
            and not _use_tag
            and not _search_context
            and not _needs_search
            and not (live_knowledge and str(live_knowledge).strip())
            and not _is_code
            and mode not in ("code",)
            and (model_key or "") != "code"
            and "[LIVE WEATHER" not in (user_message or "")
            and "Live camera" not in (user_message or "")
            and "[Live camera" not in (user_message or "")
            and "data:image/" not in (user_message or "")
        )

        try:
            if _use_tag:
                self._emit_status(status_callback, f"Using {self._get_model_name(selected_model)} + tool agent in parallel…")
                response_text = await self._tool_augmented_run(
                    user_message=user_message,
                    messages=messages,
                    tools=tools,
                    system_text=system_text,
                    stream_callback=stream_callback,
                    status_callback=status_callback,
                    primary_model=selected_model,
                )
            else:
                response_text = await asyncio.to_thread(
                    self._run_loop,
                    messages,
                    tools,
                    stream_callback,
                    status_callback,
                    approval_callback,
                    selected_model,
                    _search_task is not None,   # skip_live_route
                    _llm_cache_ok,
                )
        except Exception as exc:
            response_text = self._handle_ollama_error(exc)
            if stream_callback:
                stream_callback(response_text)

        self._memory.save_turn(session_id, "user", mem_message)
        self._memory.save_turn(session_id, "assistant", response_text)
        self._maybe_extract_facts(mem_message)

        return response_text

    def _maybe_extract_facts(self, text: str) -> None:
        lowered = text.lower().strip()
        for pattern, key in _FACT_PATTERNS:
            m = re.search(pattern, lowered, re.IGNORECASE)
            if m:
                value = m.group(1).strip().rstrip(".")
                if value:
                    self._memory.save_fact(key, _format_extracted_fact_value(key, value))

    # ── Internal loop ─────────────────────────────────────────────────

    def _run_loop(
        self,
        messages: list[dict],
        tools: list[dict],
        stream_callback: Callable[[str], None] | None,
        status_callback: Callable[[str], None] | None,
        approval_callback: Callable[[ApprovalRequest], bool] | None,
        model: str,
        skip_live_route: bool = False,
        llm_cache_ok: bool = False,
    ) -> str:
        # Downgrade model if RAM is under pressure before building options
        model = self._safe_model_for_pressure(model)

        client = ollama.Client(host=self._host)
        options = self._build_options(model)
        latest_user_message = self._latest_user_message(messages)

        direct_memory_result = self._execute_memory_request_route(latest_user_message, status_callback)
        if direct_memory_result is not None:
            if stream_callback and direct_memory_result:
                stream_callback(direct_memory_result)
            self._maybe_extract_facts(latest_user_message)
            return direct_memory_result

        # Skip the blocking sync search when orchestrator.run() already launched a
        # parallel search task (regardless of whether it succeeded or timed out).
        # The search results (if any) were injected into the system prompt by the
        # caller — doing a second search here would cause a duplicate blocking hang.
        if not skip_live_route:
            route_intent = _effective_search_query_message(latest_user_message)
            direct_live_result = self._execute_live_request_route(route_intent, status_callback)
            if direct_live_result is not None:
                if stream_callback and direct_live_result:
                    stream_callback(direct_live_result)
                return direct_live_result

        # Only models we *know* support Ollama's tool-calling API get tool schemas.
        # Using an allowlist is safer than a denylist — unknown/fine-tuned models
        # default to plain chat, which never causes a 400 error.
        _TOOL_CAPABLE_PATTERNS = (
            "qwen2.5",    # qwen2.5:72b, qwen2.5-coder:32b
            "mistral:",   # mistral:7b
            "llama3.2",   # llama3.2-vision:11b (but NOT llama3.2:3b — excluded below)
            "llama3.1",
            "llama3.3",
        )
        no_tools = (
            not tools
            or not self._registry
            or not any(p in model.lower() for p in _TOOL_CAPABLE_PATTERNS)
            or model == self._fast_model   # llama3.2:3b — too small, skip tools
        )
        if no_tools:
            self._emit_status(status_callback, "Running model inference")
            return self._stream_text(
                client, messages, stream_callback, status_callback, model, options, llm_cache_ok
            )

        keep_alive = resource_advisor.get_keep_alive()
        for _ in range(_MAX_TOOL_ROUNDS):
            self._emit_status(status_callback, "Planning the next step")
            response = client.chat(
                model=model,
                messages=messages,
                tools=tools,
                options=options,
                keep_alive=keep_alive,
            )
            msg = response.message
            tool_calls = msg.tool_calls or []

            if not tool_calls:
                # Final text response — stream it via callback then return
                text = msg.content or ""
                self._emit_status(status_callback, "Composing final response")
                if stream_callback and text:
                    stream_callback(text)
                return text

            # Tool round — convert ToolCall objects → dicts for round-trip
            tc_dicts = [
                {"function": {"name": tc.function.name, "arguments": tc.function.arguments}}
                for tc in tool_calls
            ]
            messages.append({
                "role": "assistant",
                "content": msg.content or "",
                "tool_calls": tc_dicts,
            })

            for tc in tool_calls:
                if not self._tool_allowed_for_prompt(tc.function.name, latest_user_message):
                    self._emit_status(status_callback, f"Skipping unrelated tool: {tc.function.name}")
                    messages.append(
                        {
                            "role": "tool",
                            "content": (
                                f"Tool '{tc.function.name}' skipped because it does not match the current user request. "
                                "Choose a tool that directly answers the query."
                            ),
                            "name": tc.function.name,
                        }
                    )
                    continue

                self._emit_status(status_callback, self._status_label_for_tool(tc.function.name))
                content = self._dispatch(tc.function.name, tc.function.arguments, approval_callback)
                self._emit_status(status_callback, f"Tool finished: {tc.function.name}")
                messages.append({"role": "tool", "content": content, "name": tc.function.name})

        return "[Nova: reached maximum tool iterations]"

    def _dispatch(
        self,
        name: str,
        args: dict | str,
        approval_callback: Callable[[ApprovalRequest], bool] | None,
    ) -> str:
        if self._approval:
            decision = self._approval.check(name)
            if decision == ApprovalDecision.BLOCKED:
                return f"Tool '{name}' is blocked by policy."
            if decision == ApprovalDecision.CONFIRM:
                request = self._approval.get_request(name, args if isinstance(args, dict) else {})
                allowed = self._approval.resolve(name, request.tool_input, approval_callback)
                if not allowed:
                    return f"Declined by user."

        result = self._registry.execute(name, args)
        return result.content

    _OOM_SIGNALS = ("out of memory", "oom", "cannot allocate", "insufficient memory",
                    "memory exhausted", "failed to allocate")

    def _stream_text(
        self,
        client: ollama.Client,
        messages: list[dict],
        stream_callback: Callable[[str], None] | None,
        status_callback: Callable[[str], None] | None,
        model: str,
        options: dict[str, int | float],
        use_cache: bool = False,
    ) -> str:
        # Dynamic keep_alive — shorter when RAM is tight so memory is reclaimed faster
        keep_alive = resource_advisor.get_keep_alive()

        try:
            return self._stream_text_inner(
                client, messages, stream_callback, status_callback, model, options, keep_alive, use_cache
            )
        except Exception as exc:
            err = str(exc).lower()
            if any(sig in err for sig in self._OOM_SIGNALS):
                # OOM: halve the context, disable mlock, retry once with the fast model
                print(
                    f"[ResourceAdvisor] OOM on {model} — retrying with "
                    f"{self._fast_model} at reduced context",
                    flush=True,
                )
                self._emit_status(status_callback, "Low memory — switching to lighter model")
                fallback_opts = dict(options)
                fallback_opts["num_ctx"]  = min(int(options.get("num_ctx", 2048)) // 2, 1024)
                fallback_opts["num_batch"] = 128
                fallback_opts["mlock"]    = False
                fallback_opts["use_mmap"] = True
                return self._stream_text_inner(
                    client, messages, stream_callback, status_callback,
                    self._fast_model, fallback_opts, "2m", False
                )
            raise

    def _replay_text_as_stream(
        self,
        text: str,
        stream_callback: Callable[[str], None] | None,
        status_callback: Callable[[str], None] | None,
    ) -> None:
        """Re-emit a cached string as small chunks so the client stream UX stays the same."""
        if not text:
            return
        self._emit_status(status_callback, "Using cached response")
        self._emit_status(status_callback, "Generating response")
        step = 88
        if stream_callback:
            for i in range(0, len(text), step):
                stream_callback(text[i : i + step])

    def _stream_text_inner(
        self,
        client: ollama.Client,
        messages: list[dict],
        stream_callback: Callable[[str], None] | None,
        status_callback: Callable[[str], None] | None,
        model: str,
        options: dict[str, int | float],
        keep_alive: str,
        use_cache: bool = False,
    ) -> str:
        if use_cache and self._llm_cache is not None:
            hit = self._llm_cache.get(model, messages)
            if hit is not None:
                self._replay_text_as_stream(hit, stream_callback, status_callback)
                return hit
        collected: list[str] = []
        first_token_received = False
        stream = client.chat(
            model=model,
            messages=messages,
            stream=True,
            options=options,
            keep_alive=keep_alive,
        )
        for chunk in stream:
            delta = chunk.message.content
            if delta:
                if not first_token_received:
                    self._emit_status(status_callback, "Generating response")
                    first_token_received = True
                collected.append(delta)
                if stream_callback:
                    stream_callback(delta)
        out = "".join(collected)
        if use_cache and self._llm_cache is not None and out:
            self._llm_cache.set(model, messages, out)
        return out

    @staticmethod
    def _emit_status(status_callback: Callable[[str], None] | None, text: str) -> None:
        if status_callback is None:
            return
        try:
            status_callback(text)
        except Exception:
            return

    @staticmethod
    def _status_label_for_tool(name: str) -> str:
        labels = {
            "search_web": "Searching the web",
            "get_news": "Reading latest news sources",
            "read_file": "Reading files",
            "list_files": "Inspecting project structure",
            "search_code": "Searching code",
            "git_status": "Checking git status",
            "take_screenshot": "Capturing screenshot",
            "read_note": "Reading notes",
            "write_note": "Saving notes",
            "get_clipboard": "Reading clipboard",
            "set_clipboard": "Updating clipboard",
            "find_movie": "Looking up movie information",
            "get_now_playing": "Checking media playback",
            "play_music": "Starting music playback",
            "pause_music": "Pausing music playback",
            "play_youtube": "Opening YouTube",
            "open_url": "Opening URL",
            "draft_message": "Drafting your message",
            "draft_email": "Preparing email draft",
            "send_email": "Sending email",
        }
        return labels.get(name, f"Running tool: {name}")

    @staticmethod
    def _latest_user_message(messages: list[dict]) -> str:
        for message in reversed(messages):
            if message.get("role") == "user":
                return str(message.get("content", "") or "")
        return ""

    @staticmethod
    def _is_news_request(text: str) -> bool:
        lowered = text.lower()
        # Word-boundary only — avoids substring false positives in long quoted context.
        if re.search(r"\bnews\b", lowered):
            return True
        markers = ["latest news", "news today", "headlines", "current events", "breaking news", "news update"]
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _is_weather_request(text: str) -> bool:
        """Word-boundary match only — avoid \"rain\" matching \"Ukraine\", \"strain\", \"training\"."""
        lowered = (text or "").lower()
        if re.search(
            r"\b(weather|forecast|temperatures?|humidity|overcast|drizzle|drought|hail|"
            r"snow|sleet|blizzard|tornado|thunder|hurricane|barometric|"
            r"raining|rainy|rain|stormy|storms?|precip(itation)?|"
            r"windy|winds?|breeze|breezy|fog(gy)?|muggy|"
            r"feels like|heat index|wind chill|uv index|high today|low tonight)\b",
            lowered,
        ):
            return True
        if re.search(r"\b(hot|cold|warm|cool|wet|dry) (is it| outside|out there)\b", lowered):
            return True
        if re.search(r"\b(what|how)(?:'s|s| is) the (weather|temp|temperature)\b", lowered):
            return True
        return False

    @staticmethod
    def _is_online_search_request(text: str) -> bool:
        lowered = text.lower()
        markers = [
            "search online", "look this up", "look up", "search the web",
            "find online", "browse for", "search for", "find me",
            "google", "can you search", "search up",
            "latest information", "official source", "official sources",
            "espn cricinfo", "cricinfo", "icc tournament", "icc tournaments",
            "can you tell me about", "could you tell me about", "find out about",
            "i want to know about", "read up on", "what can you find out",
        ]
        return any(marker in lowered for marker in markers)

    @staticmethod
    def _is_live_info_request(text: str) -> bool:
        lowered = text.lower()
        trigger_words = ["latest", "today", "current", "now", "live", "breaking"]
        domains = ["news", "weather", "forecast", "price", "stock", "score", "traffic", "exchange rate"]
        return any(token in lowered for token in trigger_words) and any(domain in lowered for domain in domains)

    @staticmethod
    def _factual_lookup_intent(text: str) -> bool:
        """
        Phrases that imply the user wants to *discover* or verify world facts, not
        only generative writing.  Matches mid-sentence (e.g. "hey nova can you
        tell me about X") so we still run a parallel web search.
        """
        lowered = (text or "").lower()
        phrases = (
            "tell me about",
            "can you tell me about",
            "could you tell me about",
            "do you know about",
            "what do you know about",
            "find out about",
            "i want to know about",
            "i'd like to know about",
            "read up on",
            "look this up",
            "information about",
            "facts about",
        )
        if any(p in lowered for p in phrases):
            return True
        padded = f" {lowered} "
        if re.search(
            r"(\s|^)(find out|to find out|look( this| it)? up|read up on)(\s|$)",
            padded,
        ):
            return len(lowered.split()) >= 3
        return False

    @staticmethod
    def _needs_web_search(text: str) -> bool:
        """
        Return True when the query would benefit from a web search.

        Because search now runs in PARALLEL with the LLM (5-second race), a
        slightly aggressive trigger is fine — the LLM always answers immediately
        from training data if the search is too slow.  The cost of searching
        unnecessarily is only a background network call, not a user-visible delay.
        """
        lowered = text.lower().strip()

        # Very short conversational turns — no search needed
        if len(lowered.split()) < 3:
            return False

        # Pure task requests — writing, coding, maths etc. don't need search
        task_prefixes = (
            "write ", "draft ", "help me write", "summarize ", "explain ",
            "translate ", "fix ", "debug ", "code ", "create a ", "make a ",
            "calculate ", "convert ", "generate ", "draw ", "sketch ", "paint ",
            "compose ", "poem ", "essay ", "story ",
        )
        if any(lowered.startswith(p) for p in task_prefixes):
            return False

        # Always-live data (prices, weather, scores, breaking news)
        always_live = [
            "stock price", "share price", "crypto", "bitcoin", "ethereum",
            "exchange rate", "forex", "weather", "forecast",
            "sports score", "cricket score", "football score",
            "live score", "fixtures", "standings",
            "breaking news", "news today", "latest news",
            "icc ", "espn cricinfo",
        ]
        if any(s in lowered for s in always_live):
            return True

        # Factual "current state of the world" questions — search for fresh data
        live_domains = [
            "prime minister", "president", "chancellor", "leader",
            "ceo", "chief executive", "who runs", "who leads",
            "election", "vote", "poll", "referendum",
            "population", "capital city",
            "war", "conflict", "ceasefire", "invasion",
            "earthquake", "hurricane", "flood", "disaster",
            "gdp", "inflation", "interest rate", "unemployment",
            "price of", "cost of",
            "died", "arrested", "charged", "sentenced", "released",
            "acquired", "merger", "ipo", "launched", "released",
        ]
        # Time signals push any domain to search
        time_signals = [
            "current", "currently", "latest", "recent", "today", "tonight",
            "this week", "this month", "this year", "right now",
            "just announced", "just released", "as of", "2025", "2026",
        ]
        has_time = any(s in lowered for s in time_signals)
        has_domain = any(d in lowered for d in live_domains)

        # Search if: time signal alone, domain alone, or both
        if has_time or has_domain:
            return True

        # Music / entertainment releases — training data goes stale quickly
        if any(s in lowered for s in time_signals) and any(
            m in lowered
            for m in (
                "album", "albums", "mixtape", "single", "ep ", " lp ", "soundtrack",
                "discography", "rapper", "hip-hop", "hip hop", "band", "artist",
                "song", "track", "billboard", "spotify", "grammy", "tour",
            )
        ):
            return True

        # Broad factual questions that benefit from fresh sources
        factual_starts = (
            "who is ", "who are ", "who was ", "who won ",
            "what is the ", "what are the ", "what happened ",
            "when did ", "when is ", "when was ",
            "where is ", "tell me about ", "what do you know about ",
        )
        if any(lowered.startswith(s) for s in factual_starts):
            return True

        return False

    @staticmethod
    def _is_local_vision_question(text: str) -> bool:
        """
        Camera / webcam questions must be answered from prompt context, not web search.
        Voice turns include [Live camera …] / [Utterance snapshot …] prefixes.
        """
        lowered = (text or "").lower()
        if any(
            p in lowered
            for p in ("[camera", "[live camera", "utterance snapshot", "[speaker:")
        ):
            return True
        markers = (
            "see my face",
            "see me",
            "see my hand",
            "see my hands",
            "on camera",
            "webcam",
            "camera feed",
            "do you see",
            "are you seeing",
            "can you see",
            "my face",
            "my hands",
            "tracker",
            "how many fingers",
            "which finger",
            "which fingers",
            "holding up",
        )
        return any(m in lowered for m in markers)

    @staticmethod
    def _extract_news_topic(text: str) -> str:
        lowered = text.lower().strip()
        noise = [
            "what is", "what's", "whats", "the", "latest", "news", "today",
            "give me", "show me", "tell me", "about", "please", "update",
        ]
        for token in noise:
            lowered = lowered.replace(token, " ")
        return " ".join(lowered.split())

    # Filler tokens that are never part of a place name.
    # If after stripping query words only these remain, fall back to IP-detected location.
    _LOCATION_NOISE = frozenset(
        "know at my your our their here there around nearby location loc place home "
        "current currently area region somewhere anywhere 's".split()
    )

    # Ordered from longest to shortest so multi-word phrases are stripped first.
    _QUERY_STRIP_WORDS = [
        "what is", "what's", "whats", "right now", "going to", "will it", "tell me",
        "give me", "do you", "weather", "forecast", "today", "sunny", "rainy", "cold",
        "hot", "rain", "wind", "like", "over", "will", "know", "think", "how",
        "the", "for", "you", "do", "it",
    ]

    def _extract_location_from_query(self, text: str) -> str:
        lowered = text.lower().strip()
        lowered = re.sub(r"[?!.]+", "", lowered)

        base = lowered
        for phrase in self._QUERY_STRIP_WORDS:
            # Use word boundaries so "in" doesn't mangle "London"
            base = re.sub(rf"\b{re.escape(phrase)}\b", " ", base)

        # Drop leftover punctuation and noise tokens
        tokens = [t.strip("',;:-") for t in base.split()]
        tokens = [t for t in tokens if t and t not in self._LOCATION_NOISE and len(t) > 1]
        location = " ".join(tokens).strip()
        app_home = (self._settings.app.get("user_home_location") or "").strip()
        return resolve_weather_location(
            location,
            memory_location_fact=self._memory.get_fact_value("location", ""),
            app_home_location=app_home,
            server_location_context=self._location_ctx,
        )

    @staticmethod
    def _is_memory_request(text: str) -> bool:
        lowered = text.lower().strip()
        markers = [
            "what do you know about me",
            "what do you remember about me",
            "what is my name",
            "who am i",
            "who is speaking",
            "remember my name",
            "what did i tell you",
            "what did i say",
            "what is my location",
            "where do i live",
            "what is my user name",
            "what is my preference",
            "what do you know about josh",
        ]
        return any(marker in lowered for marker in markers) or lowered.startswith("remember ")

    def _execute_memory_request_route(
        self,
        user_message: str,
        status_callback: Callable[[str], None] | None,
    ) -> str | None:
        text = (user_message or "").strip()
        if not text or not self._is_memory_request(text):
            return None

        known_name = self._memory.get_fact_value("user_name", "").strip()
        last_speaker = self._memory.get_fact_value("last_speaker", "").strip()
        facts = {fact["key"]: fact["value"] for fact in self._memory.get_facts()}

        self._emit_status(status_callback, "Checking saved memory")

        if "what is my name" in text.lower() or "who am i" in text.lower() or "what is my user name" in text.lower():
            if known_name:
                return f"You’re {known_name}."
            return "I don’t know your name yet. Say 'my name is ...' and I’ll remember it."

        if "what is my location" in text.lower() or "where do i live" in text.lower():
            location = facts.get("location", "").strip()
            if location:
                return f"You told me you live in {location}."
            return "I don’t have your location saved yet."

        if "who is speaking" in text.lower() or "what do you know about me" in text.lower() or "what do you remember about me" in text.lower():
            lines: list[str] = []
            if known_name:
                lines.append(f"name: {known_name}")
            if last_speaker and last_speaker != known_name:
                lines.append(f"last speaker: {last_speaker}")
            for key in ("workplace", "user_role", "preference", "habit", "location"):
                value = facts.get(key, "").strip()
                if value:
                    lines.append(f"{key}: {value}")
            if lines:
                return "Here’s what I remember: " + "; ".join(lines) + "."
            return "I don’t have much saved about you yet."

        if text.lower().startswith("remember "):
            note = text[len("remember "):].strip().rstrip(".")
            if note:
                self._memory.save_fact("note", note)
                return f"Got it. I’ll remember that {note}."

        return None

    async def _fetch_search_context_async(
        self,
        user_message: str,
        search_query_text: str | None = None,
    ) -> str | None:
        """
        Lightweight search helper used by the parallel-search path in run().
        Returns the raw tool result text (to be injected as LLM context), or None.
        No status callbacks — the caller emits status before launching this task.

        *search_query_text* — short question for the search API (follow-up wrappers
        stripped).  Falls back to *user_message* when omitted.
        """
        if not self._registry:
            return None
        raw_full = (user_message or "").strip()
        text = (search_query_text or raw_full).strip() or raw_full
        if not text:
            return None

        tool_result = None
        if self._is_news_request(text) and self._registry.has("get_news"):
            topic = self._extract_news_topic(text)
            tool_result = await self._registry.async_execute("get_news", {"topic": topic}, timeout=8.0)

        elif self._is_weather_request(text) and self._registry.has("get_weather"):
            location = self._extract_location_from_query(text)
            tool_result = await self._registry.async_execute("get_weather", {"location": location}, timeout=8.0)

        elif self._is_online_search_request(text) and self._registry.has("search_web"):
            query = text
            for marker in ("search online", "search the web", "look this up", "look up", "find online", "browse for"):
                query = query.lower().replace(marker, " ")
            query = " ".join(query.split()) or text
            tool_result = await self._registry.async_execute("search_web", {"query": query}, timeout=12.0)

        elif self._registry.has("search_web"):
            tool_result = await self._registry.async_execute("search_web", {"query": text}, timeout=12.0)

        if tool_result is None:
            return None
        raw = (tool_result.content or "").strip()
        return raw if raw and not _is_search_failure(raw) else None

    async def _execute_live_request_route_async(
        self,
        user_message: str,
        status_callback: Callable[[str], None] | None,
    ) -> str | None:
        if not self._registry:
            return None

        text = _effective_search_query_message((user_message or "").strip())
        if not text or self._is_memory_request(text):
            return None

        tool_result = None
        if self._is_news_request(text) and self._registry.has("get_news"):
            topic = self._extract_news_topic(text)
            self._emit_status(status_callback, "Live lookup mode enabled")
            self._emit_status(status_callback, "Fetching current headlines")
            tool_result = await self._registry.async_execute("get_news", {"topic": topic})

        elif self._is_weather_request(text) and self._registry.has("get_weather"):
            location = self._extract_location_from_query(text)
            self._emit_status(status_callback, "Live lookup mode enabled")
            self._emit_status(status_callback, "Fetching live weather data")
            tool_result = await self._registry.async_execute("get_weather", {"location": location})

        elif self._is_online_search_request(text) and self._registry.has("search_web"):
            query = text
            for marker in ("search online", "search the web", "look this up", "look up", "find online", "browse for"):
                query = query.lower().replace(marker, " ")
            query = " ".join(query.split()) or text
            self._emit_status(status_callback, "Live lookup mode enabled")
            self._emit_status(status_callback, "Searching online sources")
            tool_result = await self._registry.async_execute("search_web", {"query": query}, timeout=20.0)

        elif (
            not self._is_local_vision_question(text)
            and (self._is_live_info_request(text) or self._needs_web_search(text))
            and self._registry.has("search_web")
        ):
            self._emit_status(status_callback, "Live lookup mode enabled")
            self._emit_status(status_callback, "Searching online")
            tool_result = await self._registry.async_execute("search_web", {"query": text}, timeout=20.0)

        if tool_result is None:
            return None

        raw = tool_result.content or ""
        # If the search timed out or returned an error, fall back to LLM knowledge
        if not raw or _is_search_failure(raw):
            self._emit_status(status_callback, "Composing response")
            return None  # caller will answer from training data

        self._emit_status(status_callback, "Composing response")
        return await asyncio.to_thread(self._synthesize_from_tool, text, raw, status_callback)

    def _execute_live_request_route(
        self,
        user_message: str,
        status_callback: Callable[[str], None] | None,
    ) -> str | None:
        """Sync version used only from _run_loop (worker thread context)."""
        if not self._registry:
            return None

        text = _effective_search_query_message((user_message or "").strip())
        if not text or self._is_memory_request(text):
            return None

        tool_result = None
        if self._is_news_request(text) and self._registry.has("get_news"):
            topic = self._extract_news_topic(text)
            self._emit_status(status_callback, "Live lookup mode enabled")
            self._emit_status(status_callback, "Fetching current headlines")
            tool_result = self._registry.execute("get_news", {"topic": topic})

        elif self._is_weather_request(text) and self._registry.has("get_weather"):
            location = self._extract_location_from_query(text)
            self._emit_status(status_callback, "Live lookup mode enabled")
            self._emit_status(status_callback, "Fetching live weather data")
            tool_result = self._registry.execute("get_weather", {"location": location})

        elif self._is_online_search_request(text) and self._registry.has("search_web"):
            query = text
            for marker in ("search online", "search the web", "look this up", "look up", "find online", "browse for"):
                query = query.lower().replace(marker, " ")
            query = " ".join(query.split()) or text
            self._emit_status(status_callback, "Live lookup mode enabled")
            self._emit_status(status_callback, "Searching online sources")
            tool_result = self._registry.execute("search_web", {"query": query})

        elif (
            not self._is_local_vision_question(text)
            and (self._is_live_info_request(text) or self._needs_web_search(text))
            and self._registry.has("search_web")
        ):
            self._emit_status(status_callback, "Live lookup mode enabled")
            self._emit_status(status_callback, "Searching online")
            tool_result = self._registry.execute("search_web", {"query": text})

        if tool_result is None:
            return None

        raw = tool_result.content or ""
        # If the search timed out or returned an error, fall back to LLM knowledge
        if not raw or _is_search_failure(raw):
            self._emit_status(status_callback, "Composing response")
            return None  # caller will answer from training data

        self._emit_status(status_callback, "Composing response")
        return self._synthesize_from_tool(text, raw, status_callback)

    def _synthesize_from_tool(
        self,
        user_message: str,
        tool_content: str,
        status_callback: Callable[[str], None] | None,
    ) -> str:
        """Ask the LLM to answer the user's question from raw tool data, briefly."""
        client = ollama.Client(host=self._host)
        live_knowledge = self._memory.get_fact_value("live_knowledge_feed", "")
        system = build_system_prompt(
            self._settings, location_ctx=self._location_ctx, live_knowledge=live_knowledge
        )
        # Trim to keep only meaningful content — small models lose focus on long input
        trimmed = tool_content[:2500]
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": (
                f"Live search results:\n\n{trimmed}\n\n"
                f"User asked: {user_message}\n\n"
                "Answer directly using only the facts above. "
                "1–2 sentences max. State the key fact first. "
                "If the results don't clearly answer it, say so honestly. "
                "No bullet points, no preamble, no 'Based on the results...'. "
                "Do not say you cannot browse websites, cannot access live data, or only rely on training data "
                "when live search results are provided here. "
                "Never invent facts."
            )},
        ]
        try:
            response = client.chat(
                model=self._model,
                messages=messages,
                options={"num_predict": 80, "temperature": 0.3},
                keep_alive=self._keep_alive,
            )
            return (response.message.content or "").strip()
        except Exception:
            return tool_content

    @staticmethod
    def _tool_allowed_for_prompt(tool_name: str, user_prompt: str) -> bool:
        lowered = user_prompt.lower()
        media_tools = {"get_now_playing", "play_music", "pause_music"}
        if tool_name in media_tools:
            media_markers = ["music", "song", "spotify", "apple music", "now playing", "play", "pause", "track"]
            return any(marker in lowered for marker in media_markers)
        return True

    def _safe_model_for_pressure(self, requested: str) -> str:
        """
        Under RAM pressure, downgrade heavy models to lighter alternatives so
        we don't OOM. The user's explicit small-model selections are never changed.
        """
        tier = resource_advisor.get_model_tier()
        if tier == "full":
            return requested

        heavy_models = {self._heavy_model, self._code_model, self._mind_model,
                        self._creative_model, self._sage_model}
        # quant/reason are 7–8 B — same footprint as core/insight; treat as mid-tier
        mid_models   = {self._core_model, self._insight_model, self._chat_model,
                        self._logic_model, self._star_model, self._open_model,
                        self._quant_model, self._reason_model}

        if tier == "light":
            # Critical pressure — use the smallest model for everything
            if requested in heavy_models or requested in mid_models:
                print(
                    f"[ResourceAdvisor] RAM critical — downgrading {requested} → {self._fast_model}",
                    flush=True,
                )
                return self._fast_model
        elif tier == "mid":
            # Moderate pressure — avoid heavy models, keep mid-tier fine
            if requested in heavy_models:
                fallback = self._core_model
                print(
                    f"[ResourceAdvisor] RAM moderate — downgrading {requested} → {fallback}",
                    flush=True,
                )
                return fallback
        return requested

    def _build_options(self, model: str) -> dict[str, int | float]:
        # Start with hardware-tuned base options (GPU layers, CPU threads, batch/ctx, mmap)
        perf = resource_advisor.get_perf_options()
        options: dict[str, int | float] = {
            "num_gpu":    perf["num_gpu"],
            "num_thread": perf["num_thread"],
            "num_batch":  perf["num_batch"],
            "use_mmap":   bool(perf["use_mmap"]),
            "mlock":      bool(perf["mlock"]),
        }

        # RAM-pressure-aware defaults (already computed in resource_advisor)
        pressure_ctx = perf["num_ctx"]   # may be reduced under pressure
        config_ctx   = int(self._settings.model.get("default_num_ctx", 4096))
        # Never exceed what RAM can safely support
        default_ctx  = min(config_ctx, pressure_ctx)

        default_predict = int(self._settings.model.get("default_num_predict", 768))
        temperature     = float(self._settings.model.get("temperature", 0.7))

        options.update({
            "num_ctx":     default_ctx,
            "num_predict": default_predict,
            "temperature": temperature,
            "top_p":       float(self._settings.model.get("top_p", 0.9)),
            "top_k":       int(self._settings.model.get("top_k", 40)),
        })

        if model == self._code_model:
            cfg_code_ctx = int(self._settings.model.get("code_num_ctx", 8192))
            options["num_ctx"]     = min(cfg_code_ctx, pressure_ctx)
            options["num_predict"] = int(self._settings.model.get("code_num_predict", 8192))
            options["temperature"] = float(self._settings.model.get("code_temperature", 0.25))
        elif model == self._heavy_model:
            cfg_heavy_ctx = int(self._settings.model.get("heavy_num_ctx", 4096))
            options["num_ctx"]     = min(cfg_heavy_ctx, pressure_ctx)
            options["num_predict"] = int(self._settings.model.get("heavy_num_predict", 2048))
            options["temperature"] = float(self._settings.model.get("heavy_temperature", 0.4))
        elif model == self._quant_model:
            # Near-zero temperature: maths is deterministic — variance hurts accuracy
            cfg_quant_ctx = int(self._settings.model.get("quant_num_ctx", 4096))
            options["num_ctx"]     = min(cfg_quant_ctx, pressure_ctx)
            options["num_predict"] = int(self._settings.model.get("quant_num_predict", 2048))
            options["temperature"] = float(self._settings.model.get("quant_temperature", 0.1))
            options["top_p"]       = 0.95   # keep diverse token choices for multi-step working
            options["top_k"]       = 20     # tighter token set for numerical stability
        elif model == self._reason_model:
            # CoT reasoning can be verbose; give it room to think out loud
            cfg_reason_ctx = int(self._settings.model.get("reason_num_ctx", 8192))
            options["num_ctx"]     = min(cfg_reason_ctx, pressure_ctx)
            options["num_predict"] = int(self._settings.model.get("reason_num_predict", 4096))
            options["temperature"] = float(self._settings.model.get("reason_temperature", 0.15))
            options["top_p"]       = 0.95
            options["top_k"]       = 30
        elif model == self._fast_model:
            options["num_ctx"]     = min(2048, pressure_ctx)
            options["num_predict"] = int(
                self._settings.model.get("fast_num_predict", 512)
            )
            options["temperature"] = float(
                self._settings.model.get("fast_temperature", 0.5)
            )
        elif model == self._swift_model:
            # Nova Air: light chat — a touch cooler than the global default to cut rambling
            options["num_ctx"] = min(
                int(self._settings.model.get("swift_num_ctx", 4096)),
                pressure_ctx,
            )
            options["num_predict"] = int(
                self._settings.model.get("swift_num_predict", 768)
            )
            options["temperature"] = float(
                self._settings.model.get("swift_temperature", 0.45)
            )
        elif model == self._core_model:
            # Default route for many turns — below global 0.7 to reduce instruction-meta and tangents
            options["temperature"] = float(
                self._settings.model.get("core_temperature", min(temperature, 0.62))
            )

        return options

    @staticmethod
    def _handle_ollama_error(exc: Exception) -> str:
        msg = str(exc).lower()
        if "connection" in msg or "connect" in msg or "refused" in msg:
            return (
                "I can't reach the local model right now. "
                "Please make sure Ollama is running: `ollama serve`."
            )
        if "model" in msg and ("not found" in msg or "pull" in msg):
            return (
                "The requested model isn't available locally. "
                "Run `ollama pull qwen2.5:72b` to download it."
            )
        return f"Something went wrong communicating with the model: {exc}"

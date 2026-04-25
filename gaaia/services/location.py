from __future__ import annotations

import httpx
import math
import re
import time

_cache: dict | None = None
_cache_at: float = 0.0
_CACHE_TTL_SEC = 60.0 * 30.0  # refresh every 30 minutes


def _normalize_location(raw: dict, provider: str) -> dict | None:
    """Normalize multiple IP geolocation provider payloads to one shape."""
    if not isinstance(raw, dict):
        return None

    if provider == "ipapi":
        city = (raw.get("city") or "").strip()
        region = (raw.get("region") or "").strip()
        country = (raw.get("country_name") or raw.get("country") or "").strip()
        zip_code = str(raw.get("postal") or "").strip()
        tz = str(raw.get("timezone") or "").strip()
        lat = raw.get("latitude")
        lon = raw.get("longitude")
    elif provider == "ipwhois":
        if raw.get("success") is False:
            return None
        city = (raw.get("city") or "").strip()
        region = (raw.get("region") or "").strip()
        country = (raw.get("country") or "").strip()
        zip_code = str(raw.get("postal") or "").strip()
        tz = str((raw.get("timezone") or {}).get("id") or "").strip()
        lat = raw.get("latitude")
        lon = raw.get("longitude")
    else:
        return None

    if not city:
        return None
    try:
        lat_f = float(lat)
        lon_f = float(lon)
    except (TypeError, ValueError):
        lat_f = None
        lon_f = None

    return {
        "city": city,
        "regionName": region,
        "zip": zip_code,
        "country": country,
        "lat": lat_f,
        "lon": lon_f,
        "timezone": tz,
        "source": provider,
    }


def _haversine_km(a: dict, b: dict) -> float | None:
    la1, lo1 = a.get("lat"), a.get("lon")
    la2, lo2 = b.get("lat"), b.get("lon")
    if None in (la1, lo1, la2, lo2):
        return None
    try:
        la1f, lo1f, la2f, lo2f = map(float, (la1, lo1, la2, lo2))
    except (TypeError, ValueError):
        return None
    r = 6371.0
    dlat = math.radians(la2f - la1f)
    dlon = math.radians(lo2f - lo1f)
    s = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(la1f))
        * math.cos(math.radians(la2f))
        * math.sin(dlon / 2) ** 2
    )
    return 2 * r * math.asin(math.sqrt(s))


def _location_score(loc: dict) -> int:
    return sum(
        int(bool(loc.get(k)))
        for k in ("city", "regionName", "zip", "country", "timezone", "lat", "lon")
    )


def _pick_best_location(candidates: list[dict]) -> dict | None:
    if not candidates:
        return None
    if len(candidates) == 1:
        return candidates[0]

    c_sorted = sorted(candidates, key=_location_score, reverse=True)
    best = c_sorted[0]
    second = c_sorted[1]
    dist = _haversine_km(best, second)
    if dist is not None and dist > 120.0:
        # Providers disagree significantly; keep best-scored one but mark low confidence.
        best = {**best, "confidence": "low"}
    else:
        best = {**best, "confidence": "high" if dist is not None else "medium"}
    return best


async def get_location() -> dict | None:
    """Fetch approximate location via IP geolocation (multi-provider, cached with TTL)."""
    global _cache, _cache_at
    now = time.time()
    if _cache is not None and (now - _cache_at) < _CACHE_TTL_SEC:
        return _cache

    candidates: list[dict] = []
    try:
        async with httpx.AsyncClient(timeout=4.0) as client:
            # Provider 1: ipapi
            r1 = await client.get("https://ipapi.co/json/")
            if r1.status_code == 200:
                loc = _normalize_location(r1.json(), "ipapi")
                if loc:
                    candidates.append(loc)

            # Provider 2: ipwho.is
            r2 = await client.get("https://ipwho.is/")
            if r2.status_code == 200:
                loc = _normalize_location(r2.json(), "ipwhois")
                if loc:
                    candidates.append(loc)
    except Exception:
        pass

    chosen = _pick_best_location(candidates)
    if chosen:
        _cache = chosen
        _cache_at = now
        return _cache
    return None


def location_context(loc: dict | None) -> str:
    if not loc:
        return ""
    city = loc.get("city", "")
    region = loc.get("regionName", "")
    country = loc.get("country", "")
    zip_code = loc.get("zip", "")
    tz = loc.get("timezone", "")
    source = loc.get("source", "ip geolocation")
    parts = [p for p in [city, region, country] if p]
    label = ", ".join(parts)
    zip_str = f", ZIP: {zip_code}" if zip_code else ""
    return (
        f"\n\n# User Location\nThe user is currently in {label}{zip_str} (timezone: {tz}). "
        f"Source: {source} (approximate IP geolocation). "
        "If `user_home_location` is set in app config, treat that as the user's true city when "
        "IP geolocation disagrees. Use this for weather, local info, and time — never ask them where they are."
    )


# ── Weather: resolve "my location" / bad IP geo ─────────────────────────────

_VAGUE_WEATHER_PHRASES: frozenset[str] = frozenset(
    {
        "me", "us", "here", "home", "there", "it", "a", "an", "i", "local", "now", "today",
        "my location", "our location", "this location", "the location", "current location",
        "my area", "this area", "our area", "the area", "local area", "my place", "this place",
        "same place", "my current location", "where i am", "where we are",
    }
)


def is_vague_weather_location_phrase(s: str) -> bool:
    """
    True when a parsed place string is *not* a real query for wttr.in
    (e.g. 'my location' would otherwise be geocoded to a random or wrong place).
    """
    t = re.sub(r"\s+", " ", (s or "").strip().lower())
    if not t or len(t) < 2:
        return True
    if t in _VAGUE_WEATHER_PHRASES:
        return True
    if t in ("a", "an", "i"):
        return True
    if t.startswith("my ") and "location" in t and len(t) < 50:
        return True
    return False


def city_from_location_context_string(ctx: str) -> str:
    """
    Parse 'City, Region' (first two parts) from the # User Location block
    in `location_context` output. Used to query wttr.in for IP-based home.
    """
    if not ctx:
        return ""
    m = re.search(r"currently in ([^(]+?)(?:\s*\(|,\s*ZIP|\.\s*Source)", ctx)
    if m:
        loc = m.group(1).strip().rstrip(", ")
        parts = [p.strip() for p in loc.split(",")][:2]
        return ", ".join(p for p in parts if p)
    return ""


def resolve_weather_location(
    explicit_from_message: str,
    *,
    memory_location_fact: str = "",
    app_home_location: str = "",
    server_location_context: str = "",
) -> str:
    """
    Pick a stable wttr.in path.

    1) Explicit *named* place in the user text (e.g. London) — if not a vague phrase.
    2) `app.user_home_location` in config (when VPN/server IP is wrong).
    3) Fact `location` from memory (e.g. "I live in Miami").
    4) City from server-side IP geolocation in `location_context` string.
    5) "" — wttr.in uses *request* IP (still wrong for cloud-hosted backends).
    """
    ex = (explicit_from_message or "").strip()
    if ex and not is_vague_weather_location_phrase(ex):
        return ex
    for candidate in (app_home_location, memory_location_fact):
        c = (candidate or "").strip()
        if c and not is_vague_weather_location_phrase(c):
            return c
    from_ctx = city_from_location_context_string(server_location_context)
    if from_ctx:
        return from_ctx
    return ""

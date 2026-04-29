"""Emit the set of Ollama models GAAIA can use, filtered to what fits in this box's
unified memory budget (RAM + VRAM, or just RAM on Apple Silicon).

Reads from gaaia.services.model_router so the list always tracks the router config.
Prints one model tag per line, sorted small → large so quick wins land first.

Usage:
    python scripts/list_pullable_models.py [--headroom-gb 2]
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from gaaia.services.model_router import (  # noqa: E402
    _MODEL_RAM_GB,
    _ROLE_FALLBACKS,
    _ram_for_model,
    get_total_memory_gb,
)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--headroom-gb", type=float, default=2.0,
                    help="Reserve this much memory for the OS / app when filtering (default: 2 GB).")
    ap.add_argument("--no-ram-filter", action="store_true",
                    help="Emit every tagged model regardless of whether it fits in this box's memory. "
                         "Useful for archival pulls or pre-staging for a beefier machine.")
    args = ap.parse_args()

    budget = max(get_total_memory_gb() - args.headroom_gb, 1.0)

    # Collect unique tagged models across every role.
    seen: set[str] = set()
    for chain in _ROLE_FALLBACKS.values():
        for m in chain:
            # Skip alias entries that don't carry a tag — they collapse onto the tagged form
            # in Ollama and would just trigger an extra download attempt.
            if ":" not in m:
                continue
            seen.add(m)

    picked: list[tuple[float, str]] = []
    for m in seen:
        ram = _ram_for_model(m)
        if args.no_ram_filter or ram <= budget:
            picked.append((ram, m))

    picked.sort()  # small → large
    for _ram, m in picked:
        print(m)

    suffix = " (no RAM filter)" if args.no_ram_filter else f", budget={budget:.1f} GB"
    print(
        f"# total={len(picked)} models{suffix}, "
        f"est_disk_gb~{sum(r for r, _ in picked) * 0.6:.0f}",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

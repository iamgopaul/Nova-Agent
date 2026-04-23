"""
Nova Chart Generation Service — matplotlib backend.

Used for embedding charts as static PNG images inside documents (DOCX, PDF).
For live chat display, charts are rendered client-side with recharts.

Supported chart types: bar, line, pie, area, scatter, table
"""

from __future__ import annotations

import io
from typing import Any

import matplotlib
matplotlib.use("Agg")   # non-interactive backend — safe for server-side use
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
import numpy as np


# ── Colour palette (matches Nova's blue accent palette) ──────────────────────
_PALETTE = [
    "#2563eb",  # blue
    "#16a34a",  # green
    "#dc2626",  # red
    "#d97706",  # amber
    "#7c3aed",  # violet
    "#0891b2",  # cyan
    "#db2777",  # pink
    "#65a30d",  # lime
]

_BG   = "#0f172a"   # dark navy background
_FG   = "#e2e8f0"   # light text
_GRID = "#1e293b"   # subtle grid lines


def _style_axes(ax: plt.Axes, title: str, xlabel: str, ylabel: str) -> None:
    """Apply Nova's dark theme to a matplotlib axes."""
    ax.set_facecolor(_BG)
    ax.figure.set_facecolor(_BG)
    ax.tick_params(colors=_FG, labelsize=9)
    for spine in ax.spines.values():
        spine.set_edgecolor(_GRID)
    ax.xaxis.label.set_color(_FG)
    ax.yaxis.label.set_color(_FG)
    ax.title.set_color(_FG)
    ax.set_title(title, fontsize=13, fontweight="bold", pad=12)
    if xlabel:
        ax.set_xlabel(xlabel, fontsize=10)
    if ylabel:
        ax.set_ylabel(ylabel, fontsize=10)
    ax.grid(True, color=_GRID, linewidth=0.6, alpha=0.8)


def _to_png(fig: plt.Figure) -> bytes:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=150, bbox_inches="tight",
                facecolor=_BG, edgecolor="none")
    plt.close(fig)
    buf.seek(0)
    return buf.read()


# ── Individual chart renderers ────────────────────────────────────────────────

def _bar_chart(spec: dict) -> bytes:
    labels   = spec.get("labels", [])
    datasets = spec.get("datasets", [])
    title    = spec.get("title", "")
    xlabel   = spec.get("xlabel", "")
    ylabel   = spec.get("ylabel", "")

    n_groups = len(labels)
    n_series = len(datasets)
    x = np.arange(n_groups)
    width = 0.7 / max(n_series, 1)

    fig, ax = plt.subplots(figsize=(9, 5))
    _style_axes(ax, title, xlabel, ylabel)

    for i, ds in enumerate(datasets):
        colour = ds.get("color") or _PALETTE[i % len(_PALETTE)]
        offset = (i - (n_series - 1) / 2) * width
        ax.bar(x + offset, ds.get("data", []), width,
               label=ds.get("label", f"Series {i+1}"),
               color=colour, alpha=0.88, zorder=3)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30 if n_groups > 6 else 0, ha="right")
    if n_series > 1:
        ax.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=9)
    return _to_png(fig)


def _line_chart(spec: dict, area: bool = False) -> bytes:
    labels   = spec.get("labels", [])
    datasets = spec.get("datasets", [])
    title    = spec.get("title", "")
    xlabel   = spec.get("xlabel", "")
    ylabel   = spec.get("ylabel", "")

    x = list(range(len(labels)))
    fig, ax = plt.subplots(figsize=(9, 5))
    _style_axes(ax, title, xlabel, ylabel)

    for i, ds in enumerate(datasets):
        colour = ds.get("color") or _PALETTE[i % len(_PALETTE)]
        data = ds.get("data", [])
        ax.plot(x, data, marker="o", markersize=5, linewidth=2,
                color=colour, label=ds.get("label", f"Series {i+1}"), zorder=3)
        if area:
            ax.fill_between(x, data, alpha=0.18, color=colour)

    ax.set_xticks(x)
    ax.set_xticklabels(labels, rotation=30 if len(labels) > 6 else 0, ha="right")
    if datasets:
        ax.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=9)
    return _to_png(fig)


def _pie_chart(spec: dict) -> bytes:
    labels = spec.get("labels", [])
    data   = (spec.get("datasets") or [{}])[0].get("data", [])
    title  = spec.get("title", "")

    fig, ax = plt.subplots(figsize=(7, 6))
    ax.set_facecolor(_BG)
    fig.set_facecolor(_BG)
    ax.set_title(title, fontsize=13, fontweight="bold", color=_FG, pad=12)

    colours = _PALETTE[:len(labels)]
    wedges, texts, autotexts = ax.pie(
        data, labels=None, autopct="%1.1f%%",
        colors=colours, startangle=140,
        textprops={"color": _FG, "fontsize": 9},
        wedgeprops={"linewidth": 1, "edgecolor": _BG},
    )
    for at in autotexts:
        at.set_color(_FG)
        at.set_fontsize(8)

    patches = [mpatches.Patch(color=colours[i % len(colours)], label=lb)
               for i, lb in enumerate(labels)]
    ax.legend(handles=patches, loc="lower center",
              bbox_to_anchor=(0.5, -0.08), ncol=min(len(labels), 4),
              facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=9)
    return _to_png(fig)


def _scatter_chart(spec: dict) -> bytes:
    datasets = spec.get("datasets", [])
    title    = spec.get("title", "")
    xlabel   = spec.get("xlabel", "")
    ylabel   = spec.get("ylabel", "")

    fig, ax = plt.subplots(figsize=(8, 5))
    _style_axes(ax, title, xlabel, ylabel)

    for i, ds in enumerate(datasets):
        colour = ds.get("color") or _PALETTE[i % len(_PALETTE)]
        pts = ds.get("data", [])
        xs = [p[0] if isinstance(p, (list, tuple)) else i for i, p in enumerate(pts)]
        ys = [p[1] if isinstance(p, (list, tuple)) else p for p in pts]
        ax.scatter(xs, ys, color=colour, alpha=0.8, s=60, zorder=3,
                   label=ds.get("label", f"Series {i+1}"))

    if len(datasets) > 1:
        ax.legend(facecolor=_BG, edgecolor=_GRID, labelcolor=_FG, fontsize=9)
    return _to_png(fig)


def _table_chart(spec: dict) -> bytes:
    headers = spec.get("headers", [])
    rows    = spec.get("rows", [])
    title   = spec.get("title", "")

    col_w = max(1.2, 8.0 / max(len(headers), 1))
    row_h = 0.4
    fig_h = max(3.0, row_h * (len(rows) + 2) + 1.2)
    fig, ax = plt.subplots(figsize=(min(12, col_w * len(headers)), fig_h))
    ax.axis("off")
    fig.set_facecolor(_BG)
    ax.set_facecolor(_BG)
    if title:
        ax.set_title(title, fontsize=13, fontweight="bold", color=_FG, pad=10)

    table_data = [headers] + [[str(c) for c in row] for row in rows]
    tbl = ax.table(
        cellText=table_data[1:],
        colLabels=table_data[0],
        loc="center",
        cellLoc="center",
    )
    tbl.auto_set_font_size(False)
    tbl.set_fontsize(9)

    for (r, c), cell in tbl.get_celld().items():
        cell.set_edgecolor(_GRID)
        if r == 0:
            cell.set_facecolor("#2563eb")
            cell.set_text_props(color="white", fontweight="bold")
        elif r % 2 == 0:
            cell.set_facecolor("#1e293b")
            cell.set_text_props(color=_FG)
        else:
            cell.set_facecolor("#0f172a")
            cell.set_text_props(color=_FG)

    tbl.scale(1, 1.4)
    return _to_png(fig)


# ── Public entry point ────────────────────────────────────────────────────────

def _timeline_chart(spec: dict) -> bytes:
    """
    Render a horizontal timeline from spec["events"] list.
    Each event: {"time": str, "label": str}
    Also handles spec["labels"] + spec["datasets"][0]["data"] as fallback.
    """
    # Normalise: support both {"events": [...]} and the standard labels/datasets format
    events = spec.get("events") or []
    if not events:
        # Build from labels list
        for i, lbl in enumerate(spec.get("labels", [])):
            events.append({"time": lbl, "label": ""})

    if not events:
        return _bar_chart(spec)

    n   = len(events)
    fig_h = max(3, 1.0 + n * 0.55)
    fig, ax = plt.subplots(figsize=(12, fig_h))
    _style_axes(ax, fig)

    y_positions = list(range(n - 1, -1, -1))   # top-to-bottom

    # Central spine line
    ax.axvline(x=0.5, color="#2563eb", linewidth=2, alpha=0.4, zorder=1)

    for i, (y, event) in enumerate(zip(y_positions, events)):
        color = _PALETTE[i % len(_PALETTE)]

        # Node circle
        ax.scatter(0.5, y, s=220, color=color, zorder=3, linewidths=0)

        # Left side: time label
        ax.text(0.42, y, event.get("time", ""), ha="right", va="center",
                fontsize=8.5, color="#94a3b8", fontweight="bold")

        # Connector dash
        ax.plot([0.5, 0.58], [y, y], color=color, linewidth=1.5, alpha=0.6, zorder=2)

        # Right side: event label
        ax.text(0.60, y, event.get("label", ""), ha="left", va="center",
                fontsize=9, color="#e2e8f0",
                bbox=dict(boxstyle="round,pad=0.3", facecolor="#1e293b",
                          edgecolor=color, linewidth=0.8, alpha=0.85))

    ax.set_xlim(0, 1)
    ax.set_ylim(-0.8, n - 0.2)
    ax.axis("off")

    title = spec.get("title", "Timeline")
    ax.set_title(title, color="#e2e8f0", fontsize=13, fontweight="bold", pad=12)

    fig.tight_layout(pad=1.2)
    return _to_png(fig)


def generate_chart(spec: dict[str, Any]) -> bytes:
    """
    Render a chart from *spec* and return PNG bytes.

    spec keys:
      type       – "bar" | "line" | "pie" | "area" | "scatter" | "table"
      title      – chart/table title
      labels     – list of x-axis labels (bar / line / area / pie)
      datasets   – list of {"label": str, "data": list[number], "color"?: str}
      headers    – column headers (table only)
      rows       – list of rows (table only)
      xlabel     – x-axis label (optional)
      ylabel     – y-axis label (optional)
    """
    chart_type = spec.get("type", "bar").lower()

    if chart_type == "bar":
        return _bar_chart(spec)
    if chart_type in ("line",):
        return _line_chart(spec, area=False)
    if chart_type == "area":
        return _line_chart(spec, area=True)
    if chart_type == "pie":
        return _pie_chart(spec)
    if chart_type == "scatter":
        return _scatter_chart(spec)
    if chart_type == "table":
        return _table_chart(spec)
    if chart_type in ("timeline", "chronology", "milestones"):
        return _timeline_chart(spec)

    # Unknown type — fall back to bar
    return _bar_chart(spec)

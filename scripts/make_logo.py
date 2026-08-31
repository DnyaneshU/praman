"""Draw the Praman wordmark.

The mark is the project's argument in three shapes: Intent, Cart, Payment,
joined by two links. The first link holds. The second is snapped, and the
Payment node has come away in red — every document still intact, the
relationship between them broken, the money somewhere it should not be.

That is deliberately not a shield, a padlock or a chequemark. Those say
"security product". This says what actually goes wrong, which is the one thing
about the project a viewer will not guess.

Drawn once and exported to both SVG and PNG so there is a single source. Run:

    python scripts/make_logo.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.lines import Line2D  # noqa: E402
from matplotlib.patches import Circle  # noqa: E402

INK = "#111822"
ACCENT = "#C02B3E"
MUTED = "#5B6675"

OUT = Path("docs/brand")

#: Fonts that can actually draw प्रमाण. matplotlib has no complex-text shaping,
#: so even with one of these the conjunct is checked by eye before it ships —
#: a half-formed ligature in a wordmark is worse than no Devanagari at all.
DEVANAGARI = ("Nirmala UI", "Noto Sans Devanagari", "Mangal", "Kohinoor Devanagari")


def devanagari_font() -> str | None:
    """The first installed font that has the glyphs, or None to omit the line."""
    import matplotlib.font_manager as fm

    installed = {f.name for f in fm.fontManager.ttflist}
    return next((name for name in DEVANAGARI if name in installed), None)


def mark(ax, *, scale=1.0, ink=INK, accent=ACCENT):
    """Three mandates, two joints, the second one snapped.

    Node radius and gap sizes are all in the same arbitrary units so the whole
    mark scales from one number — and the axis limits are derived here rather
    than passed in, because hand-written limits silently clipped the red node
    off the right edge the first time the scale changed.
    """
    r = 0.30 * scale
    xs = [0.0, 1.15 * scale, 2.30 * scale]

    # Room for the stroke width on the hollow node, which is drawn centred on
    # the circle's path and so overhangs the radius.
    pad = r * 0.55
    ax.set_xlim(xs[0] - r - pad, xs[2] + r + pad)
    ax.set_ylim(-0.16 * scale - r - pad, r + pad)
    ax.set_aspect("equal")
    ax.axis("off")

    # Intent and Cart: solid, and the link between them holds.
    for x in xs[:2]:
        ax.add_patch(Circle((x, 0), r, facecolor=ink, edgecolor="none", zorder=3))
    ax.add_line(
        Line2D(
            [xs[0] + r, xs[1] - r],
            [0, 0],
            color=ink,
            linewidth=5.5 * scale,
            solid_capstyle="butt",
            zorder=2,
        )
    )

    # Payment: hollow and red. It is still a valid, signed document — which is
    # why it keeps its outline rather than being crossed out.
    ax.add_patch(
        Circle(
            (xs[2], -0.16 * scale),
            r,
            facecolor="none",
            edgecolor=accent,
            linewidth=4.5 * scale,
            zorder=3,
        )
    )

    # The snapped joint: two stubs that no longer meet, offset so the break is
    # legible at favicon size rather than reading as a dashed line.
    mid = (xs[1] + xs[2]) / 2
    ax.add_line(
        Line2D(
            [xs[1] + r, mid - 0.12 * scale],
            [0, 0],
            color=ink,
            linewidth=5.5 * scale,
            solid_capstyle="butt",
            zorder=2,
        )
    )
    ax.add_line(
        Line2D(
            [mid + 0.12 * scale, xs[2] - r],
            [-0.16 * scale, -0.16 * scale],
            color=accent,
            linewidth=5.5 * scale,
            solid_capstyle="butt",
            zorder=2,
        )
    )


def horizontal(path_stem: str, *, on_dark=False):
    """Mark left, wordmark right. The lockup for a header or a README."""
    ink = "#F2F4F7" if on_dark else INK
    muted = "#8A94A3" if on_dark else MUTED
    background = INK if on_dark else "white"

    fig = plt.figure(figsize=(8.0, 1.75), dpi=300)
    fig.patch.set_facecolor(background)

    # The mark sits on the wordmark's optical centre, close enough to read as
    # one lockup rather than as a picture beside a word.
    ax = fig.add_axes([0.025, 0.34, 0.175, 0.40])
    mark(ax, ink=ink)

    fig.text(0.215, 0.655, "PRAMAN", color=ink, fontsize=42, fontweight="bold", va="center")

    deva = devanagari_font()
    tagline = "breach and attack simulation for payment mandates"
    fig.text(
        0.218,
        0.245,
        f"प्रमाण   ·   {tagline}" if deva else tagline,
        color=muted,
        fontsize=10.5,
        va="center",
        **({"fontname": deva} if deva else {}),
    )

    for suffix in ("svg", "png"):
        fig.savefig(OUT / f"{path_stem}.{suffix}", facecolor=background, bbox_inches="tight")
    plt.close(fig)


def stacked(path_stem: str):
    """Mark over wordmark. For a card, an avatar, or a title slide."""
    fig = plt.figure(figsize=(4.0, 3.4), dpi=300)
    fig.patch.set_facecolor("white")

    ax = fig.add_axes([0.16, 0.52, 0.68, 0.30])
    mark(ax, scale=1.15)

    fig.text(0.5, 0.36, "PRAMAN", color=INK, fontsize=40, fontweight="bold", ha="center")
    if deva := devanagari_font():
        fig.text(0.5, 0.225, "प्रमाण", color=ACCENT, fontsize=15, ha="center", fontname=deva)
    fig.text(
        0.5,
        0.10,
        "breach and attack simulation\nfor agentic payment mandates",
        color=MUTED,
        fontsize=9,
        ha="center",
        linespacing=1.5,
    )

    for suffix in ("svg", "png"):
        fig.savefig(OUT / f"{path_stem}.{suffix}", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def glyph(path_stem: str):
    """The mark alone, square, for a favicon or an avatar."""
    fig = plt.figure(figsize=(2.0, 2.0), dpi=300)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0.06, 0.06, 0.88, 0.88])
    mark(ax, scale=1.0)

    for suffix in ("svg", "png"):
        fig.savefig(OUT / f"{path_stem}.{suffix}", facecolor="white", bbox_inches="tight")
    plt.close(fig)


def main() -> int:
    OUT.mkdir(parents=True, exist_ok=True)
    plt.rcParams["font.family"] = "DejaVu Sans"

    horizontal("praman-wordmark")
    horizontal("praman-wordmark-dark", on_dark=True)
    stacked("praman-stacked")
    glyph("praman-mark")

    for path in sorted(OUT.iterdir()):
        print(f"  {path}  {path.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

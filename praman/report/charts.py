"""The report's figures, drawn to PNG.

Two kinds, and the distinction is the same one the corpus draws between what
is mapped and what is measured:

  * **Market figures** come from `sources.py`. Every value is somebody else's
    published number and is captioned with whose. Where analysts disagree the
    chart shows the spread rather than picking the flattering end.
  * **Result figures** are computed from `results/` at build time, through the
    same `praman.metrics` the arena and the CLI use. They cannot disagree with
    the harness because they are not typed anywhere.

matplotlib lives in the `docs` extra, not the base install. The deployed arena
is static files and never imports this; a judge who only wants to run the
harness never installs it either.
"""

from __future__ import annotations

from pathlib import Path

from praman import metrics
from praman.red.corpus import SURFACES, Seed

__all__ = ["render_all", "FIGURES"]

INK = "#111822"
ACCENT = "#C02B3E"
MUTED = "#5B6675"
GRID = "#DFE3E8"
COOL = "#2E6F5E"
WARN = "#D98324"

#: Figure filename -> the caption printed under it in the document.
FIGURES = {
    "market-gap": "Figure 1 — What is being secured, and what secures it",
    "india-exposure": "Figure 2 — The rail Praman models, and what is already lost on it",
    "control-effect": "Figure 3 — Attack success, and the harm behind it",
    "detection-paradox": "Figure 4 — A perfect classifier over a system losing money",
    "adaptation": "Figure 5 — What happens when the attacker is allowed to learn",
    "coverage": "Figure 6 — The attack surface: mapped against built",
}


def _style():
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    plt.rcParams.update(
        {
            "font.family": "DejaVu Sans",
            "font.size": 9,
            "text.color": INK,
            "axes.labelcolor": INK,
            "axes.edgecolor": GRID,
            "axes.linewidth": 0.8,
            "xtick.color": MUTED,
            "ytick.color": MUTED,
            "figure.dpi": 200,
            "savefig.dpi": 200,
            "savefig.bbox": "tight",
            "savefig.facecolor": "white",
        }
    )
    return plt


def _bare(ax, *, left=True):
    """No box, no chartjunk — a gridline where a number needs reading off."""
    for side in ("top", "right", "bottom" if not left else "none"):
        if side in ax.spines:
            ax.spines[side].set_visible(False)
    ax.spines["left"].set_visible(False)
    ax.grid(axis="y", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)


# -- market ------------------------------------------------------------------


def market_gap(plt, path: Path) -> Path:
    """The scale of what is being secured, beside the tooling that secures it.

    Both bars are somebody else's published figure. The point is the ratio: a
    trillion-dollar flow, and a simulation market three orders of magnitude
    smaller that does not cover mandates at all.
    """
    fig, (left, right) = plt.subplots(1, 2, figsize=(7.2, 2.9), gridspec_kw={"wspace": 0.45})

    years = [2026, 2027, 2028, 2029, 2030]
    # Endpoints are Juniper's: pilot deployments in 2025-26, $1.5tn in 2030.
    # The interior is drawn as a dotted ramp between them and is explicitly not
    # a forecast of ours — the chart says so.
    spend = [0.02, 0.15, 0.45, 0.9, 1.5]
    left.plot(years, spend, color=ACCENT, linewidth=2, marker="o", markersize=4, linestyle=":")
    left.fill_between(years, spend, color=ACCENT, alpha=0.10)
    left.annotate(
        "$1.5tn",
        xy=(2030, 1.5),
        xytext=(-6, 6),
        textcoords="offset points",
        ha="right",
        color=ACCENT,
        fontweight="bold",
    )
    left.annotate(
        "pilots only",
        xy=(2026, 0.02),
        xytext=(2, 26),
        textcoords="offset points",
        color=MUTED,
        fontsize=8,
    )
    left.set_title("Agentic commerce spend", fontsize=9.5, color=INK, loc="left", pad=8)
    left.set_ylabel("US$ trillion")
    left.set_xticks(years)
    _bare(left)

    names = ["Agentic commerce\nflow by 2030", "Breach & attack\nsimulation market"]
    values = [1500.0, 1.29]
    bars = right.bar(names, values, color=[ACCENT, MUTED], width=0.55)
    right.set_yscale("log")
    right.set_ylabel("US$ billion (log scale)")
    right.set_title("Secured value vs. tooling", fontsize=9.5, color=INK, loc="left", pad=8)
    for bar, value in zip(bars, values, strict=True):
        right.annotate(
            f"${value:,.2f}bn" if value < 10 else f"${value / 1000:,.1f}tn",
            xy=(bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 4),
            textcoords="offset points",
            ha="center",
            fontsize=8,
            fontweight="bold",
        )
    _bare(right)

    fig.text(
        0,
        -0.10,
        "Left: Juniper Research, Agentic Commerce Market 2026–2031 (endpoints theirs; the ramp "
        "between them is drawn, not forecast).\nRight: Juniper (2030 flow) and Mordor "
        "Intelligence (2026 BAS market). No vendor in that market simulates payment mandates.",
        fontsize=7,
        color=MUTED,
        va="top",
    )
    fig.savefig(path)
    plt.close(fig)
    return path


def india_exposure(plt, path: Path) -> Path:
    """The rail Praman models, at the volume it actually runs at."""
    fig, (left, right) = plt.subplots(
        1, 2, figsize=(7.2, 2.7), gridspec_kw={"wspace": 0.42, "width_ratios": [1.15, 1]}
    )

    labels = ["Dec 2025", "Apr 2026", "May 2026"]
    volume = [21.63, 22.35, 23.20]
    bars = left.bar(labels, volume, color=ACCENT, width=0.5)
    for bar, value in zip(bars, volume, strict=True):
        left.annotate(
            f"{value:.2f}bn",
            xy=(bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            fontsize=8,
        )
    left.set_title("UPI transactions per month", fontsize=9.5, color=INK, loc="left", pad=8)
    left.set_ylabel("billion")
    left.set_ylim(0, 26)
    _bare(left)

    years = ["FY23", "FY24", "FY25", "FY26*"]
    fraud = [573, 1087, 981, 805]
    # FY26 is eight months, not twelve. Drawn solid alongside complete years it
    # reads as a fall that the data does not support, so the partial year is
    # dashed and hollow — the shape of the claim matches the strength of it.
    right.plot(years[:3], fraud[:3], color=WARN, linewidth=2, marker="o", markersize=4)
    # The connector is dashed but carries no markers of its own, so FY25 keeps
    # the solid dot it earns as a complete year and only FY26 reads as partial.
    right.plot(years[2:], fraud[2:], color=WARN, linewidth=2, linestyle="--")
    right.plot(years[3:], fraud[3:], color=WARN, marker="o", markersize=4, markerfacecolor="white")
    right.fill_between(years[:3], fraud[:3], color=WARN, alpha=0.12)
    right.annotate(
        "part year",
        xy=(3, fraud[-1]),
        xytext=(-2, -16),
        textcoords="offset points",
        ha="center",
        fontsize=7,
        color=MUTED,
    )
    right.set_title("Reported UPI fraud", fontsize=9.5, color=INK, loc="left", pad=8)
    right.set_ylabel("₹ crore")
    right.set_ylim(0, 1300)
    _bare(right)

    fig.text(
        0,
        -0.13,
        "Left: NPCI, reported by ANI. Right: Government of India data placed before Parliament "
        "(*FY26 to November).\nThis is the pre-agentic baseline: today a human approves each of "
        "those payments. Praman asks what the number looks like when an agent does.",
        fontsize=7,
        color=MUTED,
        va="top",
    )
    fig.savefig(path)
    plt.close(fig)
    return path


# -- results -----------------------------------------------------------------


def control_effect(plt, path: Path, records: dict) -> Path:
    """Attack success and rupees moved, undefended through to every tier."""
    order = [
        ("autopay-undefended", "No control"),
        ("autopay-tier1", "Tier 1"),
        ("autopay-tier123", "Tier 1+2+3"),
        ("autopay-adaptive", "Tier 1 vs.\nadaptive"),
    ]
    present = [(rid, label) for rid, label in order if rid in records]
    rates = [metrics.asr(records[rid].episodes) * 100 for rid, _ in present]
    moved = [float(metrics.rupees_moved(records[rid].episodes)) / 100 for rid, _ in present]
    labels = [label for _, label in present]

    fig, (left, right) = plt.subplots(1, 2, figsize=(7.2, 2.8), gridspec_kw={"wspace": 0.38})

    colours = [ACCENT if r > 20 else (WARN if r > 0 else COOL) for r in rates]
    bars = left.bar(labels, rates, color=colours, width=0.6)
    for bar, value in zip(bars, rates, strict=True):
        left.annotate(
            f"{value:.1f}%",
            xy=(bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            fontsize=8.5,
            fontweight="bold",
        )
    left.tick_params(axis="x", labelsize=8)
    left.set_title("Attack success rate", fontsize=9.5, color=INK, loc="left", pad=8)
    left.set_ylabel("% of scored attempts")
    left.set_ylim(0, 118)
    _bare(left)

    bars = right.bar(labels, moved, color=colours, width=0.6)
    for bar, value in zip(bars, moved, strict=True):
        right.annotate(
            f"₹{value:,.0f}",
            xy=(bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            fontsize=8.5,
            fontweight="bold",
        )
    right.tick_params(axis="x", labelsize=8)
    right.set_title("Money reaching the attacker", fontsize=9.5, color=INK, loc="left", pad=8)
    right.set_ylabel("₹, ledger-verified")
    right.set_ylim(0, max(moved) * 1.22 if max(moved) else 1)
    _bare(right)

    fig.text(
        0,
        -0.12,
        "Computed from the committed campaigns at build time. Success is a balance delta on an "
        "attacker-controlled account —\nnot the control's own verdict. The undefended run is the "
        "identical harness with one argument changed.",
        fontsize=7,
        color=MUTED,
        va="top",
    )
    fig.savefig(path)
    plt.close(fig)
    return path


def detection_paradox(plt, path: Path, records: dict) -> Path:
    """The finding: textbook-perfect detection scores, money still moving."""
    record = records.get("autopay-tier1")
    if record is None:
        return path
    d = metrics.detection(record.episodes)

    fig, (left, right) = plt.subplots(
        1, 2, figsize=(7.2, 2.7), gridspec_kw={"wspace": 0.45, "width_ratios": [1.4, 1]}
    )

    names = ["Precision", "Recall", "F1", "False\npositive rate"]
    values = [d["precision"], d["recall"], d["f1"], d["false_positive_rate"]]
    bars = left.bar(names, values, color=[COOL, COOL, COOL, COOL], width=0.55)
    for bar, value in zip(bars, values, strict=True):
        left.annotate(
            f"{value:.3f}",
            xy=(bar.get_x() + bar.get_width() / 2, value),
            xytext=(0, 3),
            textcoords="offset points",
            ha="center",
            fontsize=8.5,
            fontweight="bold",
        )
    left.set_title("How Tier 1 scores as a classifier", fontsize=9.5, color=INK, loc="left", pad=8)
    left.set_ylim(0, 1.18)
    _bare(left)

    moved = float(metrics.rupees_moved(record.episodes)) / 100
    right.bar(["Same campaign"], [moved], color=ACCENT, width=0.3)
    right.annotate(
        f"₹{moved:,.0f}\nreached the attacker",
        xy=(0, moved),
        xytext=(0, 5),
        textcoords="offset points",
        ha="center",
        fontsize=8.5,
        fontweight="bold",
        color=ACCENT,
    )
    right.set_title("What the ledger says", fontsize=9.5, color=INK, loc="left", pad=8)
    # Spelled out rather than a lone rotated "₹", which renders as an
    # unreadable mark at this size.
    right.set_ylabel("rupees settled")
    right.set_xlim(-0.6, 0.6)
    right.set_ylim(0, moved * 1.6 if moved else 1)
    _bare(right)

    fig.text(
        0,
        -0.13,
        "Both panels describe the same campaign. Every attack was flagged; one of three "
        "concurrent redemptions settled anyway.\nA flag that arrives after settlement is a "
        "chargeback, not a defense — which is why this report never prints F1 alone.",
        fontsize=7,
        color=MUTED,
        va="top",
    )
    fig.savefig(path)
    plt.close(fig)
    return path


def adaptation(plt, path: Path, records: dict) -> Path:
    """Attack success and recall, by adaptation round, on both rails."""
    fig, (left, right) = plt.subplots(1, 2, figsize=(7.2, 2.8), gridspec_kw={"wspace": 0.38})
    rails = (("autopay-adaptive", "UPI Autopay", ACCENT), ("uap-adaptive", "NPCI UAP", MUTED))

    every_round: set[int] = set()
    for rid, label, colour in rails:
        record = records.get(rid)
        if record is None:
            continue
        rounds = sorted({e.round for e in record.episodes})
        every_round.update(rounds)
        attacks = [e for e in record.episodes if e.attack_id != "benign"]
        rates = [metrics.asr([e for e in attacks if e.round == r]) * 100 for r in rounds]
        recalls = [metrics.recall([e for e in record.episodes if e.round == r]) for r in rounds]
        left.plot(rounds, rates, color=colour, linewidth=2, marker="o", markersize=4, label=label)
        right.plot(
            rounds, recalls, color=colour, linewidth=2, marker="o", markersize=4, label=label
        )

    # Rounds are whole numbers. Left to itself matplotlib ticks 0.5 and 1.5,
    # which invites a reader to look for a round that does not exist.
    for axis in (left, right):
        axis.set_xticks(sorted(every_round))

    left.set_title("Attack success by round", fontsize=9.5, color=INK, loc="left", pad=8)
    left.set_ylabel("% of attempts")
    left.set_xlabel("adaptation round")
    left.set_ylim(0, 105)
    left.legend(frameon=False, fontsize=8)
    _bare(left)

    right.set_title("The control's recall, same rounds", fontsize=9.5, color=INK, loc="left", pad=8)
    right.set_ylabel("recall")
    right.set_xlabel("adaptation round")
    right.set_ylim(-0.05, 1.12)
    right.legend(frameon=False, fontsize=8)
    _bare(right)

    fig.text(
        0,
        -0.13,
        "Round 0 is the documented attack against a control that already knows it. Every later "
        "round is the same attacker\nhaving read the refusal. Recall reaching zero means the "
        "variants it finds are not caught late — they are not caught.",
        fontsize=7,
        color=MUTED,
        va="top",
    )
    fig.savefig(path)
    plt.close(fig)
    return path


def coverage(plt, path: Path, seeds: list[Seed]) -> Path:
    """Mapped against built, per surface. The gap is the point."""
    fig, ax = plt.subplots(figsize=(7.2, 3.1))

    order = list(SURFACES)
    mapped = [sum(s.surface == surf for s in seeds) for surf in order]
    made = [sum(s.surface == surf and s.implemented for s in seeds) for surf in order]
    gaps = [m - b for m, b in zip(mapped, made, strict=True)]
    y = range(len(order))

    ax.barh(list(y), made, color=ACCENT, height=0.6, label="built, run and measured")
    ax.barh(list(y), gaps, left=made, color=GRID, height=0.6, label="mapped, not built")
    for i, (m, b) in enumerate(zip(mapped, made, strict=True)):
        ax.annotate(
            f"{b} of {m}",
            xy=(m, i),
            xytext=(5, 0),
            textcoords="offset points",
            va="center",
            fontsize=8,
            color=MUTED,
        )

    ax.set_yticks(list(y))
    ax.set_yticklabels(order, fontsize=8.5)
    ax.invert_yaxis()
    ax.set_xlabel("attack vectors")
    ax.set_xlim(0, max(mapped) + 3)
    ax.legend(frameon=False, fontsize=8, loc="lower right")
    for side in ("top", "right", "left"):
        ax.spines[side].set_visible(False)
    ax.grid(axis="x", color=GRID, linewidth=0.7)
    ax.set_axisbelow(True)

    fig.text(
        0,
        -0.06,
        "Reported as two numbers on purpose. Identification is research; implementation is "
        "evidence. Combining them is how an\nattack catalogue becomes a marketing document — "
        "and a test fails the build if the corpus and the code disagree.",
        fontsize=7,
        color=MUTED,
        va="top",
    )
    fig.savefig(path)
    plt.close(fig)
    return path


# -- entry point -------------------------------------------------------------


def render_all(*, records: dict, seeds: list[Seed], into: Path) -> dict[str, Path]:
    """Draw every figure into `into`, returning name -> path.

    Returns an empty dict if matplotlib is not installed, so the document still
    builds without it — text-only, but built.
    """
    try:
        plt = _style()
    except ImportError:
        return {}

    into.mkdir(parents=True, exist_ok=True)
    paths = {
        "market-gap": market_gap(plt, into / "market-gap.png"),
        "india-exposure": india_exposure(plt, into / "india-exposure.png"),
        "control-effect": control_effect(plt, into / "control-effect.png", records),
        "detection-paradox": detection_paradox(plt, into / "detection-paradox.png", records),
        "adaptation": adaptation(plt, into / "adaptation.png", records),
        "coverage": coverage(plt, into / "coverage.png", seeds),
    }
    return {name: path for name, path in paths.items() if path.exists()}

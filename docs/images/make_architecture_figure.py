#!/usr/bin/env python3
"""Draw ``docs/images/system-architecture.png``, Figure 1 of the Midterm report.

This is a diagram, not data: it has no numbers to read from the dataset, so it
is drawn here rather than in the notebook. Every figure in the report that does
carry data is produced by an executed cell of
``src/training/Midterm_Object_Sorting_RealWaste.ipynb``.

Run from the repository root:

    python3 docs/images/make_architecture_figure.py
"""

from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")

from matplotlib import font_manager
from matplotlib import pyplot as plt
from matplotlib.patches import FancyArrowPatch, FancyBboxPatch

ROOT = Path(__file__).resolve().parent.parent.parent

# The report is set in Arial, so the figures are too.
for _candidate in (
    "/usr/share/fonts/truetype/msttcorefonts/Arial.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial_Bold.ttf",
    "/usr/share/fonts/truetype/msttcorefonts/Arial_Italic.ttf",
):
    if Path(_candidate).exists():
        font_manager.fontManager.addfont(_candidate)

plt.rcParams.update(
    {
        "font.family": "sans-serif",
        "font.sans-serif": ["Arial", "Liberation Sans", "DejaVu Sans"],
        "figure.facecolor": "white",
        "axes.facecolor": "white",
    }
)

INK = "#1a1a1a"
MUTED = "#555555"


def _box(ax, x, y, w, h, title, lines, face, edge, title_size=8.8, body_size=7.5):
    """A labeled block: bold title near the top, explanation centered below it."""
    ax.add_patch(
        FancyBboxPatch(
            (x, y),
            w,
            h,
            boxstyle="round,pad=0,rounding_size=0.6",
            facecolor=face,
            edgecolor=edge,
            linewidth=1.1,
        )
    )
    cx = x + w / 2
    ax.text(cx, y + h - 0.20 * h, title, ha="center", va="center", fontsize=title_size,
            fontweight="bold", color=INK)
    ax.text(cx, y + 0.40 * h, "\n".join(lines), ha="center", va="center", fontsize=body_size,
            color="#333333", linespacing=1.6)


def _arrow(ax, start, end, color="#4a4a4a", lw=1.3, ls="-"):
    ax.add_patch(
        FancyArrowPatch(
            start,
            end,
            arrowstyle="-|>",
            mutation_scale=11,
            linewidth=lw,
            linestyle=ls,
            color=color,
            shrinkA=0,
            shrinkB=0,
        )
    )


def draw_architecture(out_path: Path) -> None:
    fig, ax = plt.subplots(figsize=(9.8, 5.6), dpi=200)
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 62)
    ax.axis("off")

    box_w, gap, x0 = 17.4, 2.3, 1.9

    def column_x(i):
        return x0 + i * (box_w + gap)

    # ---- Part A: what happens to one image at demonstration time ----------
    ax.text(0.6, 61.8, "A. Recognition pipeline (Midterm demonstration)",
            fontsize=10.5, fontweight="bold", color=INK, va="top")

    a_y, a_h = 44.0, 11.6
    ax.add_patch(
        FancyBboxPatch(
            (0.6, a_y - 1.6), 98.8, a_h + 4.6,
            boxstyle="round,pad=0,rounding_size=0.8",
            facecolor="none", edgecolor="#b3bac2", linewidth=1.0, linestyle=(0, (5, 4)),
        )
    )
    ax.text(98.4, a_y + a_h + 1.9, "Laptop or PC: every step below runs here",
            fontsize=8.0, style="italic", color=MUTED, ha="right", va="center")

    a_specs = [
        ("Image input", ["Laptop or USB webcam,", "uploaded image, or a", "groupmate's phone camera"], "#dce7f3"),
        ("Preprocessing", ["BGR to RGB, resize to", "224 x 224, rescale to", "[-1, 1] inside the model"], "#dcebe0"),
        ("MobileNetV2", ["ImageNet weights,", "fine-tuned classifier,", "5-class softmax"], "#f8e7ca"),
        ("Per-class threshold", ["Compare confidence with", "that class's own threshold", "(0.52 to 0.64)"], "#f4dde7"),
        ("Label and output", ["Class and confidence, or", "\u201cUncertain\u201d; colored border,", "banner and top-3 bars"], "#e3ddf0"),
    ]
    for i, (title, lines, face) in enumerate(a_specs):
        x = column_x(i)
        _box(ax, x, a_y, box_w, a_h, title, lines, face, "#5a6b80")
        if i:
            _arrow(ax, (x - gap, a_y + a_h / 2), (x, a_y + a_h / 2))

    # ---- the live demonstration path feeds the same first block -----------
    phone_y, phone_h = 25.0, 6.4
    relay_y, relay_h = 34.4, 5.6
    _box(ax, x0, phone_y, box_w, phone_h, "Groupmate's phone",
         ["Browser only: captures", "and sends frames"], "#f2f2f2", "#9aa3ad",
         title_size=8.2, body_size=7.2)
    _box(ax, x0, relay_y, box_w, relay_h, "Relay",
         ["Forwards frames only"], "#f2f2f2", "#9aa3ad",
         title_size=8.2, body_size=7.2)
    cx = x0 + box_w / 2
    _arrow(ax, (cx, phone_y + phone_h), (cx, relay_y), color="#8a94a0")
    _arrow(ax, (cx, relay_y + relay_h), (cx, a_y - 1.6), color="#8a94a0")

    ax.text(
        22.0, 40.0,
        "Live demonstration path. A groupmate's\n"
        "phone opens the demo page in a browser\n"
        "and streams camera frames through the\n"
        "relay. Neither the phone nor the relay\n"
        "classifies anything.",
        fontsize=8.0, style="italic", color=MUTED, va="top", linespacing=1.7,
    )

    # ---- Part B: the offline run that produced the model ------------------
    ax.text(0.6, 20.8, "B. Training and evaluation pipeline (offline, run once)",
            fontsize=10.5, fontweight="bold", color=INK, va="top")

    b_y, b_h = 4.2, 12.0
    b_specs = [
        ("RealWaste subset", ["5 classes,", "3,092 images"]),
        ("Stratified split", ["70 / 15 / 15:", "2,164 / 464 / 464"]),
        ("Preprocess, augment", ["Augmentation applied", "to the training set only"]),
        ("Two-stage training", ["Frozen backbone, then", "fine-tune last 40 layers"]),
        ("Evaluation", ["Test set once: accuracy,", "P / R / F1, confusion matrix"]),
    ]
    for i, (title, lines) in enumerate(b_specs):
        x = column_x(i)
        _box(ax, x, b_y, box_w, b_h, title, lines, "#ededed", "#9aa3ad")
        if i:
            _arrow(ax, (x - gap, b_y + b_h / 2), (x, b_y + b_h / 2))

    _arrow(ax, (column_x(3) + box_w / 2, b_y + b_h),
           (column_x(2) + box_w / 2, a_y - 1.6), color="#b06a1e", lw=1.4)
    ax.text(column_x(3) + box_w / 2 + 1.6, b_y + b_h + 3.0, "trained weights",
            fontsize=8.0, style="italic", color="#b06a1e", va="center")

    fig.savefig(out_path, bbox_inches="tight", facecolor="white", pad_inches=0.12)
    plt.close(fig)


def main() -> None:
    out = ROOT / "docs" / "images" / "system-architecture.png"
    out.parent.mkdir(parents=True, exist_ok=True)
    draw_architecture(out)
    print(f"wrote {out.relative_to(ROOT)}")


if __name__ == "__main__":
    main()

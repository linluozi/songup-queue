"""Original diagram for the README: how a song becomes a ticket.

Everything is drawn from the real code paths — the states named here
(``queue`` / ``fallback`` / ``empty``, ``seq``, quota slots, cooldown) exist in
``queue_engine.py``, and the two colours are the two page backgrounds. Nothing
in this figure is invented copy.

    python tools/make_diagram.py

Output: docs/design/ticket-flow.png (1600x900, transparent-free, warm palette)
"""

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib import font_manager
from matplotlib.patches import Circle, FancyArrowPatch, FancyBboxPatch

# A CJK face must be registered explicitly: matplotlib's default DejaVu Sans has
# no CJK glyphs, and a missing glyph renders as a box (and only as a warning).
_CJK_CANDIDATES = [
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    "/System/Library/Fonts/PingFang.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
]
for _path in _CJK_CANDIDATES:
    if os.path.exists(_path):
        font_manager.fontManager.addfont(_path)
        _name = font_manager.FontProperties(fname=_path).get_name()
        plt.rcParams["font.sans-serif"] = [_name] + plt.rcParams["font.sans-serif"]
        plt.rcParams["axes.unicode_minus"] = False
        break

INK = "#17110C"
PAPER = "#FBF5E9"
PAPER_2 = "#F6EEDF"
LINE = "#EADCC4"
BRASS = "#E0A33F"
BRASS_D = "#B97B22"
BRASS_L = "#F7E3B8"
EMBER = "#C24A2A"
OLIVE = "#6F7C3E"
STAGE = "#14100D"
STAGE_2 = "#1D1712"
MUTED = "#6B5842"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "docs", "design")


def ticket(ax, x, y, w, h, notch_side="both", fc=PAPER_2, ec=LINE, z=3, alpha=1.0):
    """A ticket stub: rounded body, two punched notches, a dashed tear."""
    ax.add_patch(
        FancyBboxPatch(
            (x, y), w, h,
            boxstyle="round,pad=0,rounding_size=0.10",
            fc=fc, ec=ec, lw=1.1, zorder=z, alpha=alpha,
        )
    )
    tear_x = x + w * 0.58
    if notch_side != "none":
        # The tear only makes sense where there are notches; without them a bare
        # dashed line reads as a rendering glitch, not as a perforation.
        ax.plot(
            [tear_x, tear_x], [y + 0.13, y + h - 0.13],
            color=BRASS_D, lw=1.0, ls=(0, (3.2, 3.0)), alpha=0.55, zorder=z + 1,
        )
    r = 0.085
    if notch_side in ("both", "top"):
        ax.add_patch(Circle((tear_x, y + h), r, color=STAGE, zorder=z + 2))
    if notch_side in ("both", "bottom"):
        ax.add_patch(Circle((tear_x, y), r, color=STAGE, zorder=z + 2))
    return tear_x


def main():
    fig = plt.figure(figsize=(16, 9), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 16)
    ax.set_ylim(0, 9)
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 16, 9, color=STAGE, zorder=0))

    for r, a in ((6.2, 0.05), (4.9, 0.055), (3.6, 0.06)):
        ax.add_patch(Circle((8, 4.55), r, fill=False, ec=BRASS, lw=1.0, alpha=a, zorder=1))

    # ---- title ------------------------------------------------------------
    ax.text(0.78, 8.30, "How a song becomes a ticket", fontsize=30, color=PAPER,
            family="serif", va="center", zorder=5)
    ax.text(0.80, 7.86, "三个状态，一次推进，两个地方同时看到",
            fontsize=15, color=BRASS, family="sans-serif", va="center", zorder=5)

    # ---- stage 1: guest adds ---------------------------------------------
    y1 = 5.35
    ticket(ax, 0.78, y1, 3.5, 1.30, notch_side="none", fc=STAGE_2, ec="#3A2E24")
    ax.text(1.02, y1 + 1.02, "① 客人递票", fontsize=15, color=BRASS,
            family="sans-serif", weight="bold", zorder=6)
    ax.text(1.02, y1 + 0.62, "POST /api/add", fontsize=12.5, color=PAPER,
            family="monospace", zorder=6)
    ax.text(1.02, y1 + 0.30, "去重 → 冷却 → 配额占位", fontsize=11.5, color="#A3917B",
            family="sans-serif", zorder=6)

    # ---- stage 2: three gates --------------------------------------------
    gx = 5.05
    gates = [
        ("去重", "在播 + 排队都算", OLIVE),
        ("冷却", "刚播过要等", BRASS),
        ("配额", "每人 max_per_user", EMBER),
    ]
    ax.text(gx, y1 + 1.62, "三道闸门，任一不过就拒", fontsize=11.5, color="#A3917B",
            family="sans-serif", zorder=6)
    for i, (name, note, colour) in enumerate(gates):
        gy = y1 + 0.98 - i * 0.52
        ax.add_patch(
            FancyBboxPatch((gx, gy), 2.35, 0.40, boxstyle="round,pad=0,rounding_size=0.07",
                           fc=STAGE_2, ec=colour, lw=1.3, zorder=4)
        )
        ax.text(gx + 0.16, gy + 0.20, name, fontsize=12, color=colour,
                family="sans-serif", weight="bold", va="center", zorder=6)
        ax.text(gx + 0.82, gy + 0.20, note, fontsize=10, color="#9C8B77",
                family="sans-serif", va="center", zorder=6)

    # ---- stage 3: the ticket --------------------------------------------
    tx, ty, tw, th = 9.10, y1 - 0.10, 4.35, 1.55
    tear = ticket(ax, tx, ty, tw, th, fc=PAPER, ec=PAPER, z=4)
    ax.text(tx + 0.28, ty + th - 0.42, "DEMO TRACK 1", fontsize=15, color=INK,
            family="serif", zorder=6)
    ax.text(tx + 0.28, ty + th - 0.78, "by guest_7bd196a0", fontsize=10.5, color=MUTED,
            family="sans-serif", zorder=6)
    # quota pips on the stub half
    for i in range(2):
        ax.add_patch(
            FancyBboxPatch((tx + 0.30 + i * 0.30, ty + 0.26), 0.22, 0.22,
                           boxstyle="round,pad=0,rounding_size=0.05",
                           fc=BRASS if i == 0 else "none",
                           ec=BRASS if i == 0 else "#C9B393", lw=1.2,
                           ls="-" if i == 0 else (0, (2, 2)), zorder=6)
        )
    ax.text(tx + 1.02, ty + 0.37, "票位 1/2", fontsize=10, color=MUTED,
            family="sans-serif", va="center", zorder=6)
    ax.text(tear + 0.20, ty + th - 0.40, "QUEUE", fontsize=9.5, color=BRASS_D,
            family="monospace", zorder=6)
    ax.text(tear + 0.20, ty + th - 0.72, "#03", fontsize=20, color=BRASS_D,
            family="monospace", zorder=6)
    ax.text(tear + 0.20, ty + 0.28, "剩余 6s", fontsize=10, color=MUTED,
            family="sans-serif", zorder=6)

    # ---- arrows ----------------------------------------------------------
    ax.add_patch(FancyArrowPatch((4.34, y1 + 0.65), (4.95, y1 + 0.65),
                                 arrowstyle="-|>", mutation_scale=15,
                                 color=BRASS, lw=1.6, zorder=5))
    ax.add_patch(FancyArrowPatch((7.48, y1 + 0.65), (9.02, y1 + 0.65),
                                 arrowstyle="-|>", mutation_scale=15,
                                 color=BRASS, lw=1.6, zorder=5))

    # ---- bottom: two surfaces, one state ---------------------------------
    ax.plot([0.78, 15.22], [4.42, 4.42], color="#3A2E24", lw=1.0, zorder=2)
    ax.text(0.78, 4.08, "同一份 status()，两个面同时看到", fontsize=11.5,
            color="#A3917B", family="sans-serif", zorder=6)

    # host surface (dark, left)
    ax.add_patch(FancyBboxPatch((0.78, 1.20), 6.55, 2.55, boxstyle="round,pad=0,rounding_size=0.14",
                                fc=STAGE_2, ec="#3A2E24", lw=1.1, zorder=3))
    ax.text(1.05, 3.42, "主机页  /host", fontsize=12.5, color=BRASS,
            family="sans-serif", weight="bold", zorder=6)
    ax.text(1.05, 3.12, "投在墙上：现在放什么、还剩几首、扫码在哪", fontsize=10.5,
            color="#9C8B77", family="sans-serif", zorder=6)
    # mini stage + stub, stacked so nothing touches the panel edge
    ax.add_patch(plt.Rectangle((1.05, 1.94), 2.62, 0.96, fc="#000000", ec="#3A2E24", zorder=4))
    ax.add_patch(plt.Polygon([[2.14, 2.20], [2.14, 2.64], [2.58, 2.42]], closed=True,
                             fc=BRASS, ec="none", zorder=5))
    ticket(ax, 1.05, 1.42, 2.62, 0.40, notch_side="none", fc=PAPER, ec=PAPER, z=4)
    ax.text(1.17, 1.62, "DEMO TRACK 1", fontsize=8.5, color=INK, family="serif",
            va="center", zorder=6)
    # mini queue
    for i in range(3):
        qy = 2.86 - i * 0.30
        ax.add_patch(FancyBboxPatch((3.92, qy), 3.16, 0.24, boxstyle="round,pad=0,rounding_size=0.05",
                                    fc="#2A211A", ec="#3A2E24", lw=0.8, zorder=4))
        ax.text(4.04, qy + 0.12, str(i + 1), fontsize=7.5, color=BRASS, family="monospace",
                va="center", zorder=6)
        ax.text(4.28, qy + 0.12, ["晴天", "天空之城", "DEMO 2"][i], fontsize=8.5,
                color=PAPER, family="sans-serif", va="center", zorder=6)

    # guest surface (paper, right)
    ax.add_patch(FancyBboxPatch((7.75, 1.20), 7.47, 2.55, boxstyle="round,pad=0,rounding_size=0.14",
                                fc=PAPER, ec=LINE, lw=1.1, zorder=3))
    ax.text(8.02, 3.42, "客人页  /", fontsize=12.5, color=BRASS_D,
            family="sans-serif", weight="bold", zorder=6)
    ax.text(8.02, 3.12, "拿在手里：还能点几首、排第几、还要等多久", fontsize=10.5,
            color=MUTED, family="sans-serif", zorder=6)
    # ticket holder
    ax.add_patch(FancyBboxPatch((8.02, 2.38), 2.30, 0.52, boxstyle="round,pad=0,rounding_size=0.08",
                                fc=PAPER_2, ec=LINE, lw=0.9, zorder=4))
    for i in range(2):
        ax.add_patch(FancyBboxPatch((8.18 + i * 0.34, 2.50), 0.26, 0.26,
                                    boxstyle="round,pad=0,rounding_size=0.05",
                                    fc=BRASS if i == 0 else "none",
                                    ec=BRASS if i == 0 else "#C9B393", lw=1.1,
                                    ls="-" if i == 0 else (0, (2, 2)), zorder=5))
    ax.text(8.98, 2.64, "还能点 1 首", fontsize=9, color=MUTED, family="sans-serif",
            va="center", zorder=6)
    # my queue entry highlighted
    ax.add_patch(FancyBboxPatch((8.02, 1.36), 6.90, 0.72, boxstyle="round,pad=0,rounding_size=0.07",
                                fc="#FDF3DC", ec=BRASS, lw=1.2, zorder=4))
    ax.text(8.20, 1.72, "03", fontsize=10, color=BRASS_D, family="monospace", va="center", zorder=6)
    ax.text(8.62, 1.72, "DEMO TRACK 1", fontsize=11, color=INK, family="sans-serif",
            va="center", zorder=6)
    ax.text(14.62, 1.72, "你 · 还要等 2 首", fontsize=9.5, color=BRASS_D, family="sans-serif",
            va="center", ha="right", zorder=6)

    # ---- footer ----------------------------------------------------------
    ax.text(0.78, 0.62, "seq 每推进一次 +1 · 播放器只在 seq 变化时重建 · 播完自动释放占位",
            fontsize=10.5, color="#7A6A58", family="sans-serif", zorder=6)
    ax.text(15.22, 0.62, "SongStub · MIT", fontsize=10.5, color=BRASS_D,
            family="monospace", ha="right", zorder=6)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "ticket-flow.png")
    fig.savefig(path, dpi=100, facecolor=STAGE)
    plt.close(fig)
    print("wrote", os.path.relpath(path, ROOT))


if __name__ == "__main__":
    main()

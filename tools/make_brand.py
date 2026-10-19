"""Original brand assets for SongStub / 曲票.

Everything here is generated, not sourced: the mark, the wordmark lockup, the
social card and the favicon all come out of this one script so they can be
regenerated after a palette change.

    python tools/make_brand.py

Outputs (docs/brand/):
    logo-mark.svg       ticket + play triangle, 24 grid
    logo-mark-dark.svg  same mark on the stage background
    wordmark.svg        horizontal lockup: mark + "SongStub" + 曲票
    social-card.png     1280x640 repo social preview
    favicon.svg         32 grid, simplified for small sizes

Licence: MIT, same as the project. No third-party artwork is used.
"""

import os
import sys

INK = "#17110C"
PAPER = "#FBF5E9"
BRASS = "#E0A33F"
BRASS_DARK = "#B97B22"
EMBER = "#C24A2A"
STAGE = "#14100D"
STAGE_MUTED = "#9C8B77"

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
OUT = os.path.join(ROOT, "docs", "brand")


def mark_svg(size=48, bg=None, stroke=BRASS, accent=BRASS, label=True):
    """The mark: a torn ticket with a play triangle punched into the tear.

    Drawn on a 24 grid and scaled, so every coordinate below is a 24-grid
    coordinate. The two notches are the same radius as the tear gap, which is
    what makes it read as "ticket" rather than "rounded rectangle".
    """
    pad = 1.5
    w = 24 - pad * 2
    h = 16
    x = pad
    y = (24 - h) / 2
    notch_r = 2.1
    tear_x = x + w * 0.56

    body = (
        "M{x:.2f},{y:.2f} "
        "h{w:.2f} "
        "a2,2 0 0 1 2,2 "
        "v{h1:.2f} "
        "a2,2 0 0 1 -2,2 "
        "h-{w:.2f} "
        "a2,2 0 0 1 -2,-2 "
        "v-{h1:.2f} "
        "a2,2 0 0 1 2,-2 z"
    ).format(x=x, y=y, w=w, h1=h - 4, h=h)

    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" '
        'width="%d" height="%d" role="img" aria-label="SongStub">' % (size, size)
    ]
    if bg:
        parts.append('<rect width="24" height="24" rx="5" fill="%s"/>' % bg)

    # Ticket body, outlined.
    parts.append(
        '<path d="%s" fill="none" stroke="%s" stroke-width="1.5" '
        'stroke-linejoin="round"/>' % (body, stroke)
    )

    # Tear line: dashed, stops short of the notches.
    parts.append(
        '<path d="M%.2f,%.2f V%.2f" stroke="%s" stroke-width="1.1" '
        'stroke-dasharray="1.4 1.5" stroke-linecap="round" opacity="0.85"/>'
        % (tear_x, y + 1.6, y + h - 1.6, stroke)
    )

    # Two notches punched at the tear line.
    for cy in (y, y + h):
        parts.append(
            '<circle cx="%.2f" cy="%.2f" r="%.2f" fill="%s"/>'
            % (tear_x, cy, notch_r, bg or "none")
        )
        if not bg:
            parts.append(
                '<circle cx="%.2f" cy="%.2f" r="%.2f" fill="none" stroke="%s" '
                'stroke-width="1.5"/>' % (tear_x, cy, notch_r, stroke)
            )

    # Play triangle on the stub (left) half.
    cx = x + w * 0.27
    cy = 12
    parts.append(
        '<path d="M%.2f,%.2f L%.2f,%.2f L%.2f,%.2f Z" fill="%s" stroke="%s" '
        'stroke-width="1.1" stroke-linejoin="round"/>'
        % (cx - 1.6, cy - 2.6, cx - 1.6, cy + 2.6, cx + 2.3, cy, accent, accent)
    )

    if label:
        # Three "stub lines" on the right half — the part that gets kept.
        for i, ly in enumerate((9.6, 12.0, 14.4)):
            lw = 4.0 if i < 2 else 2.6
            parts.append(
                '<path d="M%.2f,%.2f h%.2f" stroke="%s" stroke-width="1.1" '
                'stroke-linecap="round" opacity="0.75"/>'
                % (tear_x + 2.2, ly, lw, stroke)
            )

    parts.append("</svg>")
    return "\n".join(parts)


def favicon_svg():
    """32-grid simplification: drop the stub lines, keep mark + triangle."""
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 32 32" width="32" height="32">'
        '<rect width="32" height="32" rx="7" fill="%s"/>'
        '<path d="M7,9 h18 a2.5,2.5 0 0 1 2.5,2.5 v3 a2,2 0 0 0 0,4 v3 '
        'a2.5,2.5 0 0 1 -2.5,2.5 h-18 a2.5,2.5 0 0 1 -2.5,-2.5 v-3 '
        'a2,2 0 0 0 0,-4 v-3 a2.5,2.5 0 0 1 2.5,-2.5 z" '
        'fill="none" stroke="%s" stroke-width="2" stroke-linejoin="round"/>'
        '<path d="M13,12.2 L13,19.8 L19.4,16 Z" fill="%s"/>'
        "</svg>" % (STAGE, BRASS, BRASS)
    )


def wordmark_svg():
    """Horizontal lockup. Text is outlined paths would be ideal, but a fork
    shipped as source should stay editable — so this uses <text> with a
    system serif stack, and the raster social card is what guarantees the
    exact appearance anywhere."""
    return """<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 420 96" width="420" height="96">
  <rect width="420" height="96" rx="14" fill="{stage}"/>
  <g transform="translate(22,24) scale(2)">{mark}</g>
  <text x="96" y="52" font-family="Georgia, 'Times New Roman', serif" font-size="34"
        fill="{paper}" letter-spacing="0.4">SongStub</text>
  <text x="98" y="76" font-family="-apple-system, 'Segoe UI', 'PingFang SC', sans-serif"
        font-size="15" fill="{brass}" letter-spacing="3.2">曲票 · PARTY QUEUE</text>
</svg>""".format(
        stage=STAGE,
        paper=PAPER,
        brass=BRASS,
        mark=mark_svg(24, bg=None, label=False).split(">", 1)[1].rsplit("</svg>", 1)[0],
    )


def social_card():
    """1280x640 social preview, drawn with matplotlib so it rasterises without
    a browser. Warm editorial palette; the ticket is drawn as real geometry so
    it stays crisp at any size."""
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib.patches import Circle, FancyBboxPatch, Polygon

    fig = plt.figure(figsize=(12.8, 6.4), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 1280)
    ax.set_ylim(0, 640)
    ax.axis("off")
    ax.add_patch(plt.Rectangle((0, 0), 1280, 640, color=STAGE, zorder=0))

    # Faint concentric "stage light" rings behind the ticket.
    for r, a in ((520, 0.05), (400, 0.06), (290, 0.07)):
        ax.add_patch(Circle((330, 320), r, fill=False, ec=BRASS, lw=1.1, alpha=a, zorder=1))

    # ---- The ticket -------------------------------------------------------
    tx, ty, tw, th = 120, 196, 470, 250
    ax.add_patch(
        FancyBboxPatch(
            (tx, ty), tw, th,
            boxstyle="round,pad=0,rounding_size=18",
            fc=PAPER, ec="none", zorder=3,
        )
    )
    tear_x = tx + tw * 0.56
    # Notches: painted in the stage colour so they read as punched holes.
    for cy in (ty, ty + th):
        ax.add_patch(Circle((tear_x, cy), 21, color=STAGE, zorder=4))
    ax.plot(
        [tear_x, tear_x], [ty + 26, ty + th - 26],
        color="#C9B694", lw=2.0, ls=(0, (5, 5)), zorder=4,
    )

    # Play triangle on the stub half.
    ax.add_patch(
        Polygon(
            [[tx + 86, ty + 88], [tx + 86, ty + 162], [tx + 148, ty + 125]],
            closed=True, fc=BRASS, ec="none", zorder=5,
        )
    )

    # Stub lines on the kept half.
    for i, (ly, lw) in enumerate(((ty + 92, 128), (ty + 125, 128), (ty + 158, 86))):
        ax.plot([tear_x + 34, tear_x + 34 + lw], [ly, ly],
                color=BRASS_DARK, lw=3.0, solid_capstyle="round", alpha=0.55, zorder=5)

    # ---- Wordmark ---------------------------------------------------------
    ax.text(668, 372, "SongStub", fontsize=62, color=PAPER, family="serif",
            fontweight="normal", va="baseline", zorder=5)
    # Raster text stays ASCII on purpose: matplotlib has no guaranteed CJK font,
    # and a missing glyph renders as a box in the one image nobody can fix later.
    ax.text(672, 322, "PARTY JUKEBOX  ·  ONE TICKET PER SONG",
            fontsize=18, color=BRASS, family="sans-serif", va="baseline", zorder=5)
    ax.text(
        672, 268,
        "Fair dedup. Real player. Two faces —\none for the wall, one for the hand.",
        fontsize=15.5, color=STAGE_MUTED, family="sans-serif",
        va="top", linespacing=1.65, zorder=5,
    )

    # Footer rule + licence line.
    ax.plot([120, 1160], [118, 118], color="#3A2E24", lw=1.0, zorder=5)
    ax.text(120, 92, "MIT  ·  fork of motz0815/songup  ·  Python + Flask",
            fontsize=13, color="#7A6A58", family="sans-serif", zorder=5)
    ax.text(1160, 92, "v2.1", fontsize=13, color=BRASS, family="monospace",
            ha="right", zorder=5)

    os.makedirs(OUT, exist_ok=True)
    path = os.path.join(OUT, "social-card.png")
    fig.savefig(path, dpi=100, facecolor=STAGE)
    plt.close(fig)
    return path


def main():
    os.makedirs(OUT, exist_ok=True)
    files = {
        "logo-mark.svg": mark_svg(96, bg=None),
        "logo-mark-dark.svg": mark_svg(96, bg=STAGE),
        "favicon.svg": favicon_svg(),
        "wordmark.svg": wordmark_svg(),
    }
    for name, body in files.items():
        with open(os.path.join(OUT, name), "w", encoding="utf-8", newline="\n") as fh:
            fh.write(body + "\n")
        print("wrote docs/brand/" + name)
    card = social_card()
    print("wrote " + os.path.relpath(card, ROOT))


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""Build and verify the animated portfolio-index hero for YASLOGIST-Profile.

    python3 assets/readme/build_profile_index.py
    python3 assets/readme/build_profile_index.py --check

The artwork is an architectural schematic of this repository's public portfolio
index: one parent YASLOGIST origin branching into ten independent repositories
across three domains (4 multimodal workstreams + 1 unlinked Land vision slot,
4 independent products, and 2 computational labs), with no runtime coupling
between them.

Dependencies: Pillow only (plus standard library). Typography uses the bundled
Inter and JetBrains Mono faces in `assets/readme/fonts/`; the circular YL mark
is parsed directly from `assets/readme/yaslogist-mark.svg` via `mark.py`.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import statistics
import sys
from collections import Counter
from pathlib import Path

from PIL import (
    Image,
    ImageChops,
    ImageDraw,
    ImageFont,
    ImageSequence,
    ImageStat,
    __version__ as PILLOW_VERSION,
)

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mark import load_mark  # noqa: E402

W, H = 1920, 720
SCALE = 2
FRAMES = 200
DELAY_MS = 50  # 200 * 50 ms = 10.00 s seamless loop at 20 fps

GIF = HERE / "profile-index.gif"
POSTER = HERE / "profile-index.png"
STAMP = HERE / "profile-index.build.json"
FONT_DIR = HERE / "fonts"
ROOT = HERE.parent.parent

INPUTS = (
    HERE / "build_profile_index.py",
    HERE / "mark.py",
    HERE / "yaslogist-mark.svg",
    FONT_DIR / "Inter-ExtraBold.ttf",
    FONT_DIR / "Inter-Regular.ttf",
    FONT_DIR / "Inter-SemiBold.ttf",
    FONT_DIR / "JetBrainsMono-Regular.ttf",
    FONT_DIR / "JetBrainsMono-SemiBold.ttf",
)

# Palette tokens — deep architectural slate-petrol plate with crisp perimeter
# rule so the composition holds contrast on both GitHub dark (#0d1117) and
# light (#ffffff) backgrounds, with >= 8:1 WCAG contrast on all typography.
BG_PLATE = (10, 23, 32)
BAY_FILL = (14, 31, 42)
TILE_FILL = (18, 40, 54)
TILE_ACTIVE_BG = (26, 58, 74)
FRAME_RULE = (58, 106, 116)
HAIRLINE = (44, 82, 92)

INK_PRIMARY = (243, 248, 247)
INK_SECONDARY = (216, 233, 230)
INK_BODY = (202, 224, 220)
INK_MUTED = (166, 199, 193)

TEAL = (106, 219, 198)      # 01 Multimodal workstreams (4 linked + 1 vision)
AMBER = (234, 182, 118)     # 02 Independent products (4 linked)
CERULEAN = (125, 188, 232)  # 03 Computational labs (2 linked)

# Layout geometry — all critical elements strictly inside 5% safe inset
# ([96, 1824] x [36, 684])
HUB_X, HUB_Y = 824, 342
SPINE_X = 892
RAIL_YS = (178, 342, 506)
LABEL_NUM_X = 942
LABEL_TEXT_X = 1016
RAIL_STOP_X = 1304  # label rail terminates cleanly BEFORE air-gapped repo slots
SLOT_START_X = 1326
SLOT_SIZE = 74
SLOT_GAP = 14
GATE_OFFSET = 18    # boundary separation before the unlinked Land vision cell

RAILS = (
    ("01", "MULTIMODAL", TEAL, ("air", "ocean", "data", "intel"), True),
    ("02", "PRODUCTS", AMBER, ("urlife", "soundvis", "vip", "store"), False),
    ("03", "LABS", CERULEAN, ("uld", "orbital"), False),
)


def font(name: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), round(size * SCALE))


def sc(val: float) -> int:
    return round(val * SCALE)


def coords(points) -> list[tuple[int, int]]:
    return [(round(x * SCALE), round(y * SCALE)) for x, y in points]


def box(x0: float, y0: float, x1: float, y1: float) -> tuple[int, int, int, int]:
    return (round(x0 * SCALE), round(y0 * SCALE), round(x1 * SCALE), round(y1 * SCALE))


def draw_text(
    draw: ImageDraw.ImageDraw,
    xy: tuple[float, float],
    text: str,
    face: str,
    size: float,
    fill: tuple[int, ...],
    *,
    tracking: float = 0.0,
    anchor: str = "ls",
) -> float:
    """Draw supersampled text on an exact typographic baseline (`ls`)."""
    f = font(face, size)
    x, y = xy
    if not tracking:
        draw.text((sc(x), sc(y)), text, font=f, fill=fill, anchor=anchor)
        return f.getlength(text) / SCALE
    cursor = x
    for ch in text:
        draw.text((sc(cursor), sc(y)), ch, font=f, fill=fill, anchor="ls")
        cursor += f.getlength(ch) / SCALE + tracking
    return cursor - x


def slot_x(index: int, *, gated: bool = False) -> int:
    base = SLOT_START_X + index * (SLOT_SIZE + SLOT_GAP)
    return base + (GATE_OFFSET if gated else 0)


def draw_mark(draw: ImageDraw.ImageDraw, cx: float, cy: float, radius: float) -> None:
    """Render the repository's SVG master (`yaslogist-mark.svg`) with exact geometry."""
    geometry = load_mark()
    scaled = geometry.scaled(radius)
    half_stroke = scaled.stroke_width / 2.0
    draw.ellipse(
        box(
            cx - radius - half_stroke,
            cy - radius - half_stroke,
            cx + radius + half_stroke,
            cy + radius + half_stroke,
        ),
        fill=(2, 6, 9, 255),
        outline=(242, 246, 246, 255),
        width=max(1, sc(scaled.stroke_width)),
    )
    for idx in range(len(geometry.polygons)):
        pts = [(cx + px, cy + py) for px, py in scaled.polygon(idx)]
        draw.polygon(coords(pts), fill=(242, 246, 246, 255))


def draw_dashed_rect(
    draw: ImageDraw.ImageDraw,
    x0: float,
    y0: float,
    x1: float,
    y1: float,
    color: tuple[int, ...],
    width: int = 2,
    dash: float = 7.0,
    gap: float = 6.0,
) -> None:
    """Draw a clean dashed perimeter for the unlinked Land vision slot."""
    edges = (
        ((x0, y0), (x1, y0)),
        ((x1, y0), (x1, y1)),
        ((x1, y1), (x0, y1)),
        ((x0, y1), (x0, y0)),
    )
    w = max(1, width * SCALE)
    for (ax, ay), (bx, by) in edges:
        length = math.hypot(bx - ax, by - ay)
        ux, uy = (bx - ax) / length, (by - ay) / length
        pos = 0.0
        while pos < length:
            end = min(length, pos + dash)
            draw.line(
                coords([(ax + ux * pos, ay + uy * pos), (ax + ux * end, ay + uy * end)]),
                fill=color,
                width=w,
            )
            pos += dash + gap


def draw_repo_glyph(
    draw: ImageDraw.ImageDraw,
    kind: str,
    cx: float,
    cy: float,
    color: tuple[int, ...],
) -> None:
    """Draw a 2x-supersampled geometric glyph inside a 74x74 repository module."""
    w = round(2.3 * SCALE)
    w_thin = round(1.6 * SCALE)

    if kind == "air":
        # Swept corridor + delta airframe silhouette (YASLOGIST Air)
        draw.line(coords([(cx - 20, cy + 14), (cx + 18, cy - 14)]), fill=color, width=w_thin)
        draw.polygon(
            coords([(cx + 19, cy - 15), (cx - 4, cy - 10), (cx + 2, cy - 2), (cx + 8, cy + 9)]),
            outline=color,
            width=w,
        )
        draw.ellipse(box(cx - 22, cy + 12, cx - 16, cy + 18), fill=color)
    elif kind == "ocean":
        # Gateway container vessel hull + wave horizon (YASLOGIST Ocean)
        draw.polygon(
            coords([(cx - 19, cy - 3), (cx + 19, cy - 3), (cx + 13, cy + 6), (cx - 14, cy + 6)]),
            outline=color,
            width=w,
        )
        draw.rectangle(box(cx - 10, cy - 12, cx + 2, cy - 3), outline=color, width=w_thin)
        draw.rectangle(box(cx + 2, cy - 9, cx + 11, cy - 3), outline=color, width=w_thin)
        draw.line(
            coords([(cx - 20, cy + 14), (cx - 10, cy + 10), (cx, cy + 14), (cx + 10, cy + 10), (cx + 20, cy + 14)]),
            fill=color,
            width=w,
        )
    elif kind == "data":
        # Reconciled audit ledger rows + check spine (LOGISDATA)
        for dy, span in ((-12, 16), (0, 20), (12, 13)):
            draw.line(coords([(cx - 19, cy + dy), (cx - 19 + span * 1.5, cy + dy)]), fill=color, width=w)
            draw.ellipse(box(cx + 15, cy + dy - 2.6, cx + 20, cy + dy + 2.6), fill=color)
        draw.line(coords([(cx + 9, cy - 17), (cx + 9, cy + 17)]), fill=color, width=w_thin)
    elif kind == "intel":
        # Regional sector sweep + bearing vector (YASLOGIST Intelligence)
        draw.arc(box(cx - 19, cy - 19, cx + 19, cy + 19), start=205, end=355, fill=color, width=w)
        draw.arc(box(cx - 11, cy - 11, cx + 11, cy + 11), start=195, end=15, fill=color, width=w_thin)
        draw.line(coords([(cx, cy + 8), (cx + 14, cy - 12)]), fill=color, width=w)
        draw.ellipse(box(cx - 3.2, cy + 4.8, cx + 3.2, cy + 11.2), fill=color)
    elif kind == "land":
        # Open ground corridor (Land — unlinked roadmap direction)
        draw.line(
            coords([(cx - 18, cy + 7), (cx - 5, cy + 7), (cx + 5, cy - 7), (cx + 18, cy - 7)]),
            fill=color,
            width=w_thin,
        )
        draw.ellipse(box(cx - 21, cy + 4, cx - 15, cy + 10), outline=color, width=w_thin)
        draw.ellipse(box(cx + 15, cy - 10, cx + 21, cy - 4), outline=color, width=w_thin)
    elif kind == "urlife":
        # Three-role collaboration triad: visionaries, builders, enablers (UrLife)
        pts = [(cx, cy - 16), (cx - 16, cy + 12), (cx + 16, cy + 12)]
        draw.line(coords([pts[0], pts[1], pts[2], pts[0]]), fill=color, width=w_thin)
        for px, py in pts:
            draw.ellipse(
                box(px - 4.5, py - 4.5, px + 4.5, py + 4.5),
                fill=(*TILE_FILL, 255),
                outline=color,
                width=w,
            )
    elif kind == "soundvis":
        # Symmetric 5-band audio-reactive spectrum columns (SOUNDVIS)
        heights = (8, 16, 22, 14, 9)
        for idx, h_half in enumerate(heights):
            bx = cx + (idx - 2) * 8.5
            draw.line(coords([(bx, cy - h_half), (bx, cy + h_half)]), fill=color, width=w)
    elif kind == "vip":
        # Faceted luxury concierge diamond emblem (VIP Motors Atelier)
        draw.polygon(
            coords([(cx, cy - 19), (cx + 18, cy), (cx, cy + 19), (cx - 18, cy)]),
            outline=color,
            width=w,
        )
        draw.polygon(
            coords([(cx, cy - 9), (cx + 9, cy), (cx, cy + 9), (cx - 9, cy)]),
            outline=color,
            width=w_thin,
        )
    elif kind == "store":
        # Edge storefront parcel / tote frame (YAS Store)
        draw.rectangle(box(cx - 16, cy - 7, cx + 16, cy + 18), outline=color, width=w)
        draw.arc(box(cx - 9, cy - 18, cx + 9, cy - 1), start=180, end=360, fill=color, width=w)
        draw.line(coords([(cx - 16, cy + 1), (cx + 16, cy + 1)]), fill=color, width=w_thin)
    elif kind == "uld":
        # Isometric 3D LD3/AKE aviation container with lower-deck angled base chamfer (3D-Containers)
        front = [
            (cx - 20, cy - 11),
            (cx + 8, cy - 11),
            (cx + 8, cy + 7),
            (cx - 1, cy + 17),
            (cx - 20, cy + 17),
        ]
        top_face = [
            (cx - 20, cy - 11),
            (cx - 9, cy - 19),
            (cx + 19, cy - 19),
            (cx + 8, cy - 11),
        ]
        side_face = [
            (cx + 8, cy - 11),
            (cx + 19, cy - 19),
            (cx + 19, cy - 1),
            (cx + 10, cy + 9),
            (cx - 1, cy + 17),
            (cx + 8, cy + 7),
        ]
        draw.polygon(coords(top_face), outline=color, width=w_thin)
        draw.polygon(coords(side_face), outline=color, width=w_thin)
        draw.polygon(coords(front), outline=color, width=w)
        draw.line(coords([(cx - 6, cy - 11), (cx - 6, cy + 17)]), fill=color, width=w_thin)
    elif kind == "orbital":
        # Planet disc + terminator + inclined orbital ellipse (Orbital Earth / yastera)
        draw.ellipse(box(cx - 13, cy - 13, cx + 13, cy + 13), outline=color, width=w)
        draw.arc(box(cx - 8, cy - 13, cx + 8, cy + 13), start=270, end=90, fill=color, width=w_thin)
        orbit = []
        for step in range(37):
            ang = 2 * math.pi * step / 36
            ox = 22.5 * math.cos(ang)
            oy = 7.5 * math.sin(ang)
            rx = ox * math.cos(-0.42) - oy * math.sin(-0.42)
            ry = ox * math.sin(-0.42) + oy * math.cos(-0.42)
            orbit.append((cx + rx, cy + ry))
        draw.line(coords(orbit), fill=color, width=w_thin)


def render_tile_sprite(
    accent: tuple[int, int, int],
    glyph: str,
    *,
    active: bool,
    dashed: bool = False,
) -> Image.Image:
    """Pre-render a single 74x74 module tile at 2x supersampling and Lanczos downsample."""
    pad = 4
    dim = SLOT_SIZE + pad * 2
    hi = Image.new("RGBA", (dim * SCALE, dim * SCALE), (0, 0, 0, 0))
    d = ImageDraw.Draw(hi, "RGBA")
    x0, y0 = float(pad), float(pad)
    x1, y1 = x0 + SLOT_SIZE, y0 + SLOT_SIZE
    cut = 12.0
    poly = [(x0, y0), (x1 - cut, y0), (x1, y0 + cut), (x1, y1), (x0, y1)]

    if dashed:
        draw_dashed_rect(d, x0, y0, x1, y1, (*accent, 125), width=2, dash=7, gap=6)
        draw_repo_glyph(d, glyph, x0 + SLOT_SIZE / 2, y0 + SLOT_SIZE / 2, (*accent, 145))
    elif not active:
        glyph_rgb = tuple(round(accent[k] * 0.72 + 18) for k in range(3))
        d.polygon(coords(poly), fill=(*TILE_FILL, 255))
        d.line(coords(poly + [poly[0]]), fill=(*accent, 115), width=2 * SCALE)
        draw_repo_glyph(d, glyph, x0 + SLOT_SIZE / 2, y0 + SLOT_SIZE / 2, (*glyph_rgb, 235))
    else:
        blended_bg = tuple(round(TILE_ACTIVE_BG[k] * 0.72 + accent[k] * 0.28) for k in range(3))
        d.polygon(coords(poly), fill=(*blended_bg, 255))
        d.line(coords(poly + [poly[0]]), fill=(*accent, 255), width=round(2.5 * SCALE))
        d.line(coords([(x0 + 2, y1 - 2), (x1 - 2, y1 - 2)]), fill=(*accent, 255), width=4 * SCALE)
        draw_repo_glyph(d, glyph, x0 + SLOT_SIZE / 2, y0 + SLOT_SIZE / 2, (*INK_PRIMARY, 255))

    return hi.resize((dim, dim), Image.Resampling.LANCZOS)


class AtlasAssets:
    """Pre-rendered 2x-supersampled static plate and tile sprites for crisp animation."""

    def __init__(self) -> None:
        self.pad = 4
        self.active_tiles: dict[tuple[int, str], Image.Image] = {}
        self.base = self._build_base()

    def _build_base(self) -> Image.Image:
        im = Image.new("RGB", (W * SCALE, H * SCALE), BG_PLATE)
        d = ImageDraw.Draw(im, "RGBA")

        # Crisp outer plate frame so the dark canvas separates cleanly on both
        # GitHub dark (#0d1117) and light (#ffffff) backgrounds.
        d.rectangle(box(2, 2, W - 3, H - 3), outline=(*FRAME_RULE, 195), width=2 * SCALE)

        # Architectural portfolio bay on the right (chamfered top-right folio sheet)
        bay_poly = [
            (766, 52),
            (1788, 52),
            (1816, 80),
            (1816, 668),
            (766, 668),
        ]
        d.polygon(coords(bay_poly), fill=(*BAY_FILL, 255))
        d.line(coords(bay_poly + [bay_poly[0]]), fill=(*HAIRLINE, 215), width=round(1.5 * SCALE))

        # Balanced left registration ticks inside the 5% safe zone [96..1824, 36..684]
        tick = (94, 162, 156, 170)
        d.line(coords([(100, 76), (100, 52), (124, 52)]), fill=tick, width=2 * SCALE)
        d.line(coords([(100, 644), (100, 668), (124, 668)]), fill=tick, width=2 * SCALE)

        # ---- Left Editorial Lockup (Primary >= 64 px, Secondary >= 36 px) ----
        draw_text(d, (120, 194), "YASLOGIST", "Inter-ExtraBold.ttf", 100, (*INK_PRIMARY, 255))
        draw_text(d, (120, 302), "PROFILE", "Inter-ExtraBold.ttf", 100, (*INK_SECONDARY, 255))

        # Proportional 4 : 4 : 2 domain rule matching the 10 linked repositories
        rule_y = 344
        d.line(coords([(122, rule_y), (250, rule_y)]), fill=(*TEAL, 255), width=5 * SCALE)
        d.line(coords([(262, rule_y), (390, rule_y)]), fill=(*AMBER, 255), width=5 * SCALE)
        d.line(coords([(402, rule_y), (466, rule_y)]), fill=(*CERULEAN, 255), width=5 * SCALE)

        draw_text(
            d,
            (120, 412),
            "Public Portfolio Index",
            "Inter-SemiBold.ttf",
            42,
            (*INK_BODY, 255),
        )
        draw_text(
            d,
            (120, 470),
            "10 repos  /  3 domains",
            "JetBrainsMono-Regular.ttf",
            36,
            (*INK_MUTED, 255),
        )

        # Separator + Hero Brand Signature (#1 of 3 placements, generous margin above tick)
        d.line(coords([(120, 526), (694, 526)]), fill=(*HAIRLINE, 215), width=SCALE)
        draw_mark(d, 154, 590, 31)
        draw_text(
            d,
            (206, 603),
            "YASLOGIST.COM",
            "JetBrainsMono-SemiBold.ttf",
            36,
            (*TEAL, 255),
            tracking=0.8,
        )

        # ---- Right Portfolio Topology Bay (Origin Hub -> Spine -> 4(+1) / 4 / 2) ----
        d.line(coords([(HUB_X, HUB_Y), (SPINE_X, HUB_Y)]), fill=(96, 160, 156, 180), width=2 * SCALE)
        d.line(
            coords([(SPINE_X, RAIL_YS[0]), (SPINE_X, RAIL_YS[-1])]),
            fill=(96, 160, 156, 180),
            width=2 * SCALE,
        )
        # Origin datum crosshairs + ring
        d.line(coords([(HUB_X - 24, HUB_Y), (HUB_X - 17, HUB_Y)]), fill=(*TEAL, 140), width=round(1.5 * SCALE))
        d.line(coords([(HUB_X, HUB_Y - 24), (HUB_X, HUB_Y - 17)]), fill=(*TEAL, 140), width=round(1.5 * SCALE))
        d.line(coords([(HUB_X, HUB_Y + 17), (HUB_X, HUB_Y + 24)]), fill=(*TEAL, 140), width=round(1.5 * SCALE))
        d.ellipse(
            box(HUB_X - 13, HUB_Y - 13, HUB_X + 13, HUB_Y + 13),
            fill=(*BG_PLATE, 255),
            outline=(*TEAL, 215),
            width=2 * SCALE,
        )

        for r_idx, ((num, title, accent, glyphs, has_vision), ry) in enumerate(zip(RAILS, RAIL_YS)):
            d.line(coords([(SPINE_X, ry), (LABEL_NUM_X - 16, ry)]), fill=(*accent, 145), width=2 * SCALE)
            d.ellipse(
                box(SPINE_X - 6, ry - 6, SPINE_X + 6, ry + 6),
                fill=(*BAY_FILL, 255),
                outline=(*accent, 215),
                width=2 * SCALE,
            )

            draw_text(
                d,
                (LABEL_NUM_X, ry + 13),
                num,
                "JetBrainsMono-SemiBold.ttf",
                36,
                (*accent, 255),
            )
            draw_text(
                d,
                (LABEL_TEXT_X, ry + 14),
                title,
                "Inter-SemiBold.ttf",
                40,
                (*INK_PRIMARY, 255),
            )

            # Rail baseline terminates cleanly BEFORE the repository tiles so
            # every repository module remains visually and structurally air-gapped.
            d.line(
                coords([(LABEL_NUM_X, ry + 31), (RAIL_STOP_X, ry + 31)]),
                fill=(*accent, 75),
                width=round(1.5 * SCALE),
            )
            d.line(
                coords([(RAIL_STOP_X, ry + 25), (RAIL_STOP_X, ry + 37)]),
                fill=(*accent, 110),
                width=round(1.5 * SCALE),
            )

            if has_vision:
                top = ry - SLOT_SIZE // 2
                vx = slot_x(len(glyphs), gated=True)
                gate_x = vx - GATE_OFFSET // 2 - 2
                d.line(
                    coords([(gate_x, top + 8), (gate_x, top + SLOT_SIZE - 8)]),
                    fill=(*accent, 155),
                    width=2 * SCALE,
                )

        caption = "SCHEMATIC INDEX  /  NOT LIVE"
        cap_font = font("JetBrainsMono-Regular.ttf", 36)
        cap_w = cap_font.getlength(caption) / SCALE
        draw_text(
            d,
            (1786 - cap_w, 630),
            caption,
            "JetBrainsMono-Regular.ttf",
            36,
            (*INK_MUTED, 255),
        )

        plate = im.resize((W, H), Image.Resampling.LANCZOS).convert("RGBA")

        # Composite crisp 2x-Lanczos inactive & dashed tiles onto the base plate,
        # and cache matching 2x-Lanczos active sprites for animation blending.
        for r_idx, ((_, _, accent, glyphs, has_vision), ry) in enumerate(zip(RAILS, RAIL_YS)):
            top = ry - SLOT_SIZE // 2
            for g_name in glyphs:
                self.active_tiles[(r_idx, g_name)] = render_tile_sprite(accent, g_name, active=True)
            for idx, g_name in enumerate(glyphs):
                sx = slot_x(idx)
                inactive = render_tile_sprite(accent, g_name, active=False)
                plate.alpha_composite(inactive, (sx - self.pad, top - self.pad))
            if has_vision:
                vx = slot_x(len(glyphs), gated=True)
                vision_sprite = render_tile_sprite(accent, "land", active=False, dashed=True)
                plate.alpha_composite(vision_sprite, (vx - self.pad, top - self.pad))

        return plate.convert("RGB")


def smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3.0 - 2.0 * x)


def ease_in_out(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return 0.5 - 0.5 * math.cos(math.pi * x)


def coupler_state(
    phase: float,
) -> tuple[float, float, tuple[float, float, float], tuple[float, float, float]]:
    """Compute periodic coupler (x, y), per-rail activation, and per-rail sweep progress."""
    p = phase % 1.0
    strengths = [0.0, 0.0, 0.0]
    sweeps = [0.0, 0.0, 0.0]

    if p < 0.05:
        u = ease_in_out(p / 0.05)
        cx = HUB_X + (SPINE_X - HUB_X) * u
        cy = float(HUB_Y)
    elif p < 0.12:
        u = ease_in_out((p - 0.05) / 0.07)
        cx = float(SPINE_X)
        cy = HUB_Y + (RAIL_YS[0] - HUB_Y) * u
    elif p < 0.39:
        cx, cy = float(SPINE_X), float(RAIL_YS[0])
        local = (p - 0.12) / 0.27
        strengths[0] = smoothstep(local / 0.18) * smoothstep((1.0 - local) / 0.18)
        sweeps[0] = ease_in_out(min(1.0, local / 0.62))
    elif p < 0.46:
        u = ease_in_out((p - 0.39) / 0.07)
        cx = float(SPINE_X)
        cy = RAIL_YS[0] + (RAIL_YS[1] - RAIL_YS[0]) * u
    elif p < 0.68:
        cx, cy = float(SPINE_X), float(RAIL_YS[1])
        local = (p - 0.46) / 0.22
        strengths[1] = smoothstep(local / 0.20) * smoothstep((1.0 - local) / 0.20)
        sweeps[1] = ease_in_out(min(1.0, local / 0.62))
    elif p < 0.74:
        u = ease_in_out((p - 0.68) / 0.06)
        cx = float(SPINE_X)
        cy = RAIL_YS[1] + (RAIL_YS[2] - RAIL_YS[1]) * u
    elif p < 0.89:
        cx, cy = float(SPINE_X), float(RAIL_YS[2])
        local = (p - 0.74) / 0.15
        strengths[2] = smoothstep(local / 0.24) * smoothstep((1.0 - local) / 0.24)
        sweeps[2] = ease_in_out(min(1.0, local / 0.58))
    elif p < 0.95:
        u = ease_in_out((p - 0.89) / 0.06)
        cx = float(SPINE_X)
        cy = RAIL_YS[2] + (HUB_Y - RAIL_YS[2]) * u
    else:
        u = ease_in_out((p - 0.95) / 0.05)
        cx = SPINE_X + (HUB_X - SPINE_X) * u
        cy = float(HUB_Y)

    return cx, cy, tuple(strengths), tuple(sweeps)


def render_dynamic_overlay(
    cx: float,
    cy: float,
    phase: float,
    strengths: tuple[float, float, float],
    sweeps: tuple[float, float, float],
    *,
    poster: bool,
) -> tuple[Image.Image, tuple[int, int]]:
    """Render spine coupler, vernier phase arc, and rail lines at 2x supersampling."""
    x0, y0, x1, y1 = 788, 120, 1796, 566
    ow, oh = x1 - x0, y1 - y0
    hi = Image.new("RGBA", (ow * SCALE, oh * SCALE), (0, 0, 0, 0))
    d = ImageDraw.Draw(hi, "RGBA")

    def lc(pts):
        return [(round((px - x0) * SCALE), round((py - y0) * SCALE)) for px, py in pts]

    def lb(ax0, ay0, ax1, ay1):
        return (
            round((ax0 - x0) * SCALE),
            round((ay0 - y0) * SCALE),
            round((ax1 - x0) * SCALE),
            round((ay1 - y0) * SCALE),
        )

    for idx, ((_, _, accent, glyphs, has_vision), ry) in enumerate(zip(RAILS, RAIL_YS)):
        s = strengths[idx]
        sw = sweeps[idx]
        if s <= 0.005:
            continue

        alpha = round(235 * s)
        d.line(lc([(SPINE_X, ry), (LABEL_NUM_X - 14, ry)]), fill=(*accent, alpha), width=3 * SCALE)
        d.polygon(
            lc([(LABEL_NUM_X - 18, ry - 7), (LABEL_NUM_X - 6, ry), (LABEL_NUM_X - 18, ry + 7)]),
            fill=(*accent, alpha),
        )

        # Label rail sweep ends cleanly at RAIL_STOP_X before the air-gapped tiles
        label_reach = min(1.0, sw / 0.35) if not poster else 1.0
        sweep_end = LABEL_NUM_X + (RAIL_STOP_X - LABEL_NUM_X) * ease_in_out(label_reach)
        d.line(lc([(LABEL_NUM_X, ry + 31), (sweep_end, ry + 31)]), fill=(*accent, alpha), width=3 * SCALE)
        if label_reach > 0.92:
            stop_alpha = round(alpha * smoothstep((label_reach - 0.92) / 0.08))
            d.line(
                lc([(RAIL_STOP_X, ry + 24), (RAIL_STOP_X, ry + 38)]),
                fill=(*accent, stop_alpha),
                width=3 * SCALE,
            )

        # Arrest gate highlight before the unlinked 5th Multimodal slot (Land)
        if has_vision and sw > 0.84:
            top = ry - SLOT_SIZE // 2
            gate_alpha = round(235 * s * smoothstep((sw - 0.84) / 0.16))
            vx = slot_x(len(glyphs), gated=True)
            gate_x = vx - GATE_OFFSET // 2 - 2
            d.line(
                lc([(gate_x, top + 6), (gate_x, top + SLOT_SIZE - 6)]),
                fill=(*accent, gate_alpha),
                width=round(3.5 * SCALE),
            )

    # Continuous 1-cycle vernier bearing arc around Origin Hub (uniform 200-frame cadence,
    # exact periodicity at phase=0 and phase=1).
    angle_deg = (phase % 1.0) * 360.0 if not poster else 315.0
    arc_r = 20.0
    d.arc(
        lb(HUB_X - arc_r, HUB_Y - arc_r, HUB_X + arc_r, HUB_Y + arc_r),
        start=angle_deg - 42.0,
        end=angle_deg + 42.0,
        fill=(*TEAL, 195),
        width=2 * SCALE,
    )

    if poster:
        d.ellipse(lb(HUB_X - 5.5, HUB_Y - 5.5, HUB_X + 5.5, HUB_Y + 5.5), fill=(*INK_PRIMARY, 255))
        for (_, _, accent, _, _), ry in zip(RAILS, RAIL_YS):
            d.ellipse(lb(SPINE_X - 5.5, ry - 5.5, SPINE_X + 5.5, ry + 5.5), fill=(*accent, 255))
    else:
        d.ellipse(
            lb(cx - 11.5, cy - 11.5, cx + 11.5, cy + 11.5),
            fill=(106, 219, 198, 56),
            outline=(164, 238, 223, 220),
            width=2 * SCALE,
        )
        d.ellipse(lb(cx - 4.8, cy - 4.8, cx + 4.8, cy + 4.8), fill=(*INK_PRIMARY, 255))

    return hi.resize((ow, oh), Image.Resampling.LANCZOS), (x0, y0)


def render_frame(atlas: AtlasAssets, phase: float, *, poster: bool = False) -> Image.Image:
    """Composite one periodic animation frame using 2x-supersampled elements."""
    im = atlas.base.convert("RGBA")

    if poster:
        cx, cy = float(SPINE_X), float(HUB_Y)
        strengths = (0.82, 0.82, 0.82)
        sweeps = (1.0, 1.0, 1.0)
    else:
        cx, cy, strengths, sweeps = coupler_state(phase)

    # Blend discrete 2x-Lanczos active repository tiles across air-gaps
    for r_idx, ((_, _, _, glyphs, _), ry) in enumerate(zip(RAILS, RAIL_YS)):
        s = strengths[r_idx]
        sw = sweeps[r_idx]
        if s <= 0.005:
            continue
        top = ry - SLOT_SIZE // 2
        n_slots = len(glyphs)
        for g_idx, g_name in enumerate(glyphs):
            start_t = 0.22 + 0.56 * (g_idx / max(1, n_slots))
            slot_reach = smoothstep((sw - start_t) / 0.22) if not poster else 1.0
            tile_s = s * slot_reach
            if tile_s <= 0.01:
                continue
            sprite = atlas.active_tiles[(r_idx, g_name)]
            if tile_s < 0.995:
                r, g, b, a = sprite.split()
                a = a.point(lambda px, factor=tile_s: round(px * factor))
                sprite = Image.merge("RGBA", (r, g, b, a))
            sx = slot_x(g_idx)
            im.alpha_composite(sprite, (sx - atlas.pad, top - atlas.pad))

    dyn, offset = render_dynamic_overlay(cx, cy, phase, strengths, sweeps, poster=poster)
    im.alpha_composite(dyn, offset)
    return im.convert("RGB")


def make_palette(atlas: AtlasAssets) -> Image.Image:
    """Build one shared 256-colour palette sampling all acts so static text never crawls."""
    thumb = (W // 4, H // 4)
    picks = 12
    cols, rows = 4, 3
    sheet = Image.new("RGB", (thumb[0] * cols, thumb[1] * rows))
    for index in range(picks):
        sample = render_frame(atlas, index / picks).resize(thumb, Image.Resampling.LANCZOS)
        sheet.paste(sample, ((index % cols) * thumb[0], (index // cols) * thumb[1]))
    return sheet.quantize(
        colors=256,
        method=Image.Quantize.MAXCOVERAGE,
        dither=Image.Dither.NONE,
    )


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def provenance() -> dict:
    """Record source and output SHA-256 hashes for staleness verification."""
    return {
        "generator": str(Path(__file__).resolve().relative_to(ROOT)),
        "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in INPUTS},
        "artwork": {
            path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
            for path in (GIF, POSTER)
        },
        "canvas": [W, H],
        "frames": FRAMES,
        "delay_ms": DELAY_MS,
        "duration_ms": FRAMES * DELAY_MS,
        "renderer": {"pillow": PILLOW_VERSION},
        "note": "Hashes detect stale files; rasterization can vary across Pillow/FreeType versions.",
    }


def write_stamp() -> None:
    STAMP.write_text(json.dumps(provenance(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_stamp() -> None:
    stamp = json.loads(STAMP.read_text(encoding="utf-8"))
    current = provenance()
    for key in ("generator", "inputs", "artwork", "canvas", "frames", "delay_ms", "duration_ms"):
        if stamp.get(key) != current[key]:
            raise ValueError(f"Build stamp mismatch in {key}; rebuild both profile-index assets")


def build() -> None:
    atlas = AtlasAssets()
    render_frame(atlas, 0.0, poster=True).save(POSTER, optimize=True)
    palette = make_palette(atlas)
    frames = [
        render_frame(atlas, i / FRAMES).quantize(palette=palette, dither=Image.Dither.NONE)
        for i in range(FRAMES)
    ]
    frames[0].save(
        GIF,
        save_all=True,
        append_images=frames[1:],
        duration=DELAY_MS,
        loop=0,
        optimize=True,
        disposal=1,
        comment=b"YASLOGIST-Profile: schematic portfolio index (10 repos, 3 domains), not live data.",
    )
    write_stamp()
    print(f"Wrote {GIF.name}, {POSTER.name} and {STAMP.name}")
    check()


def difference(a: Image.Image, b: Image.Image) -> tuple[float, float]:
    """Mean luminance change and RGB-exact changed pixel fraction on decoded frames."""
    delta = ImageChops.difference(a, b)
    red, green, blue = delta.split()
    any_channel = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    changed = 1.0 - any_channel.histogram()[0] / (W * H)
    return ImageStat.Stat(delta.convert("L")).mean[0], changed


def check() -> None:
    """Verify the encoded GIF, PNG poster, loop seam, brightness smoothness, and stamp."""
    check_stamp()
    with GIF.open("rb") as handle:
        if handle.read(6) != b"GIF89a":
            raise ValueError("Hero is not GIF89a")
        handle.seek(-1, 2)
        if handle.read(1) != b";":
            raise ValueError("GIF trailer is missing or has trailing data")
    with Image.open(POSTER) as still:
        if still.format != "PNG" or still.size != (W, H) or getattr(still, "n_frames", 1) != 1:
            raise ValueError("Poster must be a static 1920 x 720 PNG")
        still.verify()
    with Image.open(GIF) as hero:
        if hero.format != "GIF" or hero.size != (W, H) or hero.info.get("loop") != 0:
            raise ValueError("Hero must be a 1920 x 720 looping GIF")
        if b"not live data" not in hero.info.get("comment", b"").lower():
            raise ValueError("Hero is missing its schematic-data provenance")
        duration = 0
        first = previous = None
        changes = []
        delays = Counter()
        brightness_std = []
        brightness_mean = []
        count = 0
        for frame in ImageSequence.Iterator(hero):
            delay = frame.info.get("duration", 0)
            if delay <= 0:
                raise ValueError("A frame has no positive display duration")
            delays[delay] += 1
            duration += delay
            rgb = frame.convert("RGB")
            if rgb.size != (W, H):
                raise ValueError("Frame has the wrong dimensions")
            sample = rgb.convert("L").resize((240, 90), Image.Resampling.BILINEAR)
            stat = ImageStat.Stat(sample)
            brightness_std.append(stat.stddev[0])
            brightness_mean.append(stat.mean[0])
            if previous is not None:
                changes.append(difference(previous, rgb))
            else:
                first = rgb.copy()
            previous = rgb
            count += 1
        if count < 2 or first is None or previous is None:
            raise ValueError("The hero is not an animation")
        if duration != FRAMES * DELAY_MS:
            raise ValueError(f"Wrong total duration: {duration} ms")
        if min(brightness_std) < 10:
            raise ValueError("A decoded frame appears blank")
        brightness_jumps = [abs(b - a) for a, b in zip(brightness_mean, brightness_mean[1:])]
        brightness_jumps.append(abs(brightness_mean[-1] - brightness_mean[0]))
        brightness_jump = max(brightness_jumps)
        if brightness_jump > 1.5:
            raise ValueError(f"A frame has an abrupt global brightness jump: {brightness_jump:.2f}/255")
        seam = difference(previous, first)
        median_changed = statistics.median(value[1] for value in changes)
        peak_changed = max(value[1] for value in changes)
        if peak_changed <= 0.0001:
            raise ValueError("No meaningful non-text motion was detected")
        if seam[1] > max(0.002, median_changed * 5):
            raise ValueError(f"The loop boundary changes unusually many pixels: {seam[1]:.5f}")
    print(
        f"GIF: {W} x {H}, {count} decoded frames, {duration / 1000:.2f} s, "
        f"loop=infinite, {GIF.stat().st_size:,} bytes"
    )
    print(f"Frame delays: {dict(sorted(delays.items()))} ms")
    print(
        f"Motion: median {median_changed * 100:.3f}% pixels/step; "
        f"peak {peak_changed * 100:.3f}%; seam {seam[1] * 100:.3f}%"
    )
    print(f"Maximum global brightness step: {brightness_jump:.3f}/255")
    print(f"Poster: {W} x {H}, {POSTER.stat().st_size:,} bytes; all frames decoded")
    print("Source and artwork hashes match the build stamp")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="inspect existing GIF and PNG")
    parser.add_argument("--poster-only", action="store_true", help="render the static plate only")
    args = parser.parse_args()
    if args.check:
        check()
    elif args.poster_only:
        render_frame(AtlasAssets(), 0.0, poster=True).save(POSTER, optimize=True)
        print(f"Wrote {POSTER.name}")
    else:
        build()


if __name__ == "__main__":
    main()

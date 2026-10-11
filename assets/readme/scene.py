#!/usr/bin/env python3
"""YASLOGIST profile hero - cinematic scene renderer.

This module holds the art direction and procedural drawing code for the
YASLOGIST profile hero: a seamless, pre-rendered motion piece that GitHub
can display with no JavaScript, no video player and no external hosting.

Everything here is drawn from primitives (vector paths, gradients, real
type) by Pillow + NumPy. Nothing is downloaded and nothing is a stock
asset. `build_hero.py` drives it.

Honesty note carried from the repository: the artwork is a *schematic*
system map of the public portfolio. The route lines are illustrative
gateway metaphors, not live operational data, and the scene is labelled
that way on screen.
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

# --------------------------------------------------------------------------
# Canvas / timing
# --------------------------------------------------------------------------
W, H = 1920, 720                  # master composition (as documented)
SS = 2                            # supersample factor -> 3840 x 1440 working canvas
MARGIN = 26                       # slack around the design frame for camera drift

FRAMES = 200                      # 200 @ 50 ms = 10.0 s seamless loop
DELAY_MS = 50
TAU = math.tau

# Design frame (the composition is authored in this space, origin top-left).
INSET = 26
LEFT = 64
RIGHT = W - 64

# --------------------------------------------------------------------------
# Brand tokens - lifted from the repository's existing artwork so the whole
# profile keeps one visual system.
# --------------------------------------------------------------------------
INK = (244, 248, 248)             # brand white (matches the YL mark)
INK_SOFT = (206, 226, 226)

LAND = (93, 235, 215)             # cyan   - land / platform
OCEAN = (109, 181, 237)           # blue   - ocean / freight
AIR = (254, 181, 118)             # amber  - air / planning
TEAL_MUTE = (113, 201, 207)
SLATE = (135, 167, 181)
AMBER_MUTE = (211, 160, 108)

BG_TOP = (10, 25, 39)
BG_BOTTOM = (4, 11, 18)

MODES = (
    ("LAND", "PLATFORM VISION", LAND, True),
    ("OCEAN", "SEA-FREIGHT DEMO", OCEAN, False),
    ("AIR", "AIR-FREIGHT SIM", AIR, False),
)

# Gateway spokes radiating from the brand's home city. Geographic
# coordinates are real; the links are illustrative, as labelled on screen.
ORIGIN = ("CAI", 30.0, 31.2)
GATEWAYS = (
    ("RTM", 51.9, 4.5),
    ("PIR", 37.9, 23.6),
    ("JED", 21.5, 39.2),
    ("JIB", 11.6, 43.1),
    ("MBA", -4.0, 39.7),
    ("DUR", -29.9, 31.0),
    ("BOM", 19.0, 72.9),
)

GLOBE_CX, GLOBE_CY, GLOBE_R = 1452.0, 358.0, 268.0
CAMBER = -31.2                    # initial longitude placed at disc centre
TILT = 19.0                       # north-pole lean, degrees

FONT_DIR = Path(__file__).resolve().parent / "fonts"


# --------------------------------------------------------------------------
# Colour helpers
# --------------------------------------------------------------------------
def mix(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def fade(c, alpha):
    """Return an RGBA tuple for a colour at a given opacity."""
    return (int(c[0]), int(c[1]), int(c[2]), int(max(0.0, min(1.0, alpha)) * 255))


def rgb(c):
    return (int(c[0]), int(c[1]), int(c[2]))


# --------------------------------------------------------------------------
# Easing / timing (all periodic in the loop length, so the loop is seamless)
# --------------------------------------------------------------------------
def smoothstep(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3.0 - 2.0 * x)


def ease_in_out_sine(x):
    return 0.5 - 0.5 * math.cos(math.pi * max(0.0, min(1.0, x)))


def sway(p, cycles=1.0, phase=0.0):
    """Bounded, perfectly periodic oscillation in [-1, 1]."""
    return math.sin(TAU * (cycles * p + phase))


def pulse_env(t, fade_in=0.10, power=1.6):
    """A pulse envelope that is exactly 0 at t=0 and t=1.

    Expanding rings and lane pulses must vanish at the loop seam, otherwise
    they would pop in at full brightness on the next cycle.
    """
    t = t % 1.0
    rise = smoothstep(min(1.0, t / fade_in))
    return rise * (1.0 - t) ** power


def ensemble(p):
    """The four-act dramatic envelope (0..1), periodic in the loop.

    Act I emergence -> Act II activation -> Act III peak -> Act IV resolve,
    folded back to the opening state so frame N is frame 0.
    """
    return 0.58 + 0.42 * smoothstep(0.5 - 0.5 * math.cos(TAU * p))


# --------------------------------------------------------------------------
# Type
# --------------------------------------------------------------------------
class Typo:
    """Letter-spaced text drawing at supersampled scale."""

    def __init__(self, ss: int):
        self.ss = ss
        self.cache: dict[tuple[str, int], ImageFont.FreeTypeFont] = {}

    def f(self, name: str, size: float) -> ImageFont.FreeTypeFont:
        px = max(1, int(round(size * self.ss)))
        key = (name, px)
        if key not in self.cache:
            self.cache[key] = ImageFont.truetype(str(FONT_DIR / name), px)
        return self.cache[key]

    def measure(self, s: str, name: str, size: float, tracking: float = 0.0) -> float:
        if not s:
            return 0.0
        fo = self.f(name, size)
        return (sum(fo.getlength(c) for c in s) + tracking * (len(s) - 1)) / self.ss

    def draw(self, d: ImageDraw.ImageDraw, xy, s: str, name: str, size: float,
             fill, tracking: float = 0.0, anchor: str = "la", align: str | None = None,
             halo: float = 0.0, halo_rgb=(0, 0, 0)) -> float:
        """Draw letter-spaced text at supersampled coordinates.

        xy is in supersampled px. `align` may be 'c' or 'r' to shift the run
        so it stays centred / right-aligned after tracking is applied.
        Returns the run width in supersampled px.
        """
        if not s:
            return 0.0
        fo = self.f(name, size)
        tr = tracking * self.ss
        x, y = xy
        total = sum(fo.getlength(c) for c in s) + tr * (len(s) - 1)
        if align == "c":
            x -= total / 2.0
        elif align == "r":
            x -= total
        cx = x
        halo_fill = (*halo_rgb, 200) if halo else None
        for ch in s:
            d.text((cx, y), ch, font=fo, fill=fill, anchor="l" + anchor[1],
                   stroke_width=int(round(halo * self.ss)) if halo else 0,
                   stroke_fill=halo_fill)
            cx += fo.getlength(ch) + tr
        return total


# --------------------------------------------------------------------------
# Geometry
# --------------------------------------------------------------------------
def project(lat: float, lon: float, spin: float, cx: float, cy: float, r: float):
    """Orthographic globe projection. Returns (x, y, depth) in design px."""
    la, lo = math.radians(lat), math.radians(lon + spin)
    cl = math.cos(la)
    x = cl * math.sin(lo)
    y = math.sin(la)
    z = cl * math.cos(lo)
    t = math.radians(TILT)
    y2 = y * math.cos(t) - z * math.sin(t)
    z2 = y * math.sin(t) + z * math.cos(t)
    return cx + r * x, cy - r * y2, z2


def bezier(p0, p1, p2, s):
    u = 1.0 - s
    return (u * u * p0[0] + 2 * u * s * p1[0] + s * s * p2[0],
            u * u * p0[1] + 2 * u * s * p1[1] + s * s * p2[1])


def bezier3(p0, p1, p2, p3, s):
    u = 1.0 - s
    return (u**3 * p0[0] + 3 * u * u * s * p1[0] + 3 * u * s * s * p2[0] + s**3 * p3[0],
            u**3 * p0[1] + 3 * u * u * s * p1[1] + 3 * u * s * s * p2[1] + s**3 * p3[1])


def arc_path(points, color, width, alpha=1.0):
    """Build a (points, fill, width) tuple list for ImageDraw.line."""
    return (points, fade(color, alpha), width)


def glow_dot(em: Image.Image, xy, radius, color, alpha=1.0, ss=SS):
    """Soft luminous point: solid core plus a wide, faint halo."""
    d = ImageDraw.Draw(em, "RGBA")
    x, y = xy[0] * ss, xy[1] * ss
    r = radius * ss
    d.ellipse([x - r * 3.4, y - r * 3.4, x + r * 3.4, y + r * 3.4],
              fill=fade(color, alpha * 0.055))
    d.ellipse([x - r * 1.9, y - r * 1.9, x + r * 1.9, y + r * 1.9],
              fill=fade(color, alpha * 0.16))
    d.ellipse([x - r, y - r, x + r, y + r], fill=fade(color, alpha))

# --------------------------------------------------------------------------
# Layout constants (design px)
# --------------------------------------------------------------------------
HEADER_BASE = 56.0
RULE_Y = 88.0
MAST_BASE = 306.0
TAG_BASE = 352.0
ACCENT_Y = 372.0
SECTION_BASE = 410.0
LANE_BASE = (452.0, 494.0, 536.0)
RAIL_DY = -11.0
RAIL_X0, RAIL_X1 = 300.0, 748.0
BUS_X = 770.0
BAR_Y0, BAR_Y1 = 556.0, 590.0
BAR_BASE = 581.0
FOOT_BASE_1, FOOT_BASE_2 = 646.0, 672.0

BEARING_R = 314.0
# (rx, ry, rotation, cycles-per-loop, colour, alpha, rotating?)
ORBIT_RINGS = ((346.0, 104.0, 16.0, 0.5, LAND, 0.24, True),
               (352.0, 136.0, 158.0, 0.0, OCEAN, 0.19, False))


# --------------------------------------------------------------------------
# Layer 01 - atmosphere
# --------------------------------------------------------------------------
def build_background() -> Image.Image:
    """Gradients, blooms, an engineering graticule and film grain."""
    w, h = (W + MARGIN * 2) * SS, (H + MARGIN * 2) * SS
    base = np.zeros((h, w, 3), dtype=np.float32)

    ys = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    for c in range(3):
        base[:, :, c] = BG_TOP[c] + (BG_BOTTOM[c] - BG_TOP[c]) * (ys ** 0.85)

    def blob(cxp, cyp, r, color, strength):
        px, py = (cxp + MARGIN) * SS, (cyp + MARGIN) * SS
        rr = r * SS
        x0, x1 = max(0, int(px - rr)), min(w, int(px + rr))
        y0, y1 = max(0, int(py - rr)), min(h, int(py + rr))
        if x1 <= x0 or y1 <= y0:
            return
        gx = np.arange(x0, x1, dtype=np.float32)[None, :] - px
        gy = np.arange(y0, y1, dtype=np.float32)[:, None] - py
        fall = np.clip(1.0 - np.sqrt(gx * gx + gy * gy) / rr, 0.0, 1.0) ** 2.6
        for c in range(3):
            base[y0:y1, x0:x1, c] += fall * strength * color[c]

    blob(GLOBE_CX, GLOBE_CY, 640, (30, 104, 126), 0.46)
    blob(GLOBE_CX - 170, GLOBE_CY + 200, 420, (96, 62, 34), 0.26)
    blob(GLOBE_CX + 250, GLOBE_CY - 160, 460, (26, 62, 104), 0.28)
    blob(430, 300, 660, (18, 62, 80), 0.24)
    blob(1420, 700, 600, (14, 44, 62), 0.20)

    # Engineering graticule, faded to the mid-field.
    grid = Image.new("L", (w, h), 0)
    gd = ImageDraw.Draw(grid)
    step = 64 * SS
    for i, x in enumerate(range(0, w, step)):
        gd.line([(x, 0), (x, h)], fill=26 if i % 4 else 46, width=SS)
    for j, y in enumerate(range(0, h, step)):
        gd.line([(0, y), (w, y)], fill=26 if j % 4 else 46, width=SS)
    gx = np.linspace(0.0, 1.0, w, dtype=np.float32)[None, :]
    gy = np.linspace(0.0, 1.0, h, dtype=np.float32)[:, None]
    mask = (np.clip(np.sin(np.pi * gx), 0, None) ** 0.6) * \
           (np.clip(np.sin(np.pi * gy), 0, None) ** 0.5)
    base += (np.asarray(grid, dtype=np.float32) / 255.0)[:, :, None] * \
            np.array([58, 116, 132], dtype=np.float32) * mask[:, :, None]

    img = Image.fromarray(np.clip(base, 0, 255).astype(np.uint8), "RGB")
    layer = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    ld = ImageDraw.Draw(layer, "RGBA")
    rng = np.random.default_rng(90210)
    for i in range(210):
        x = (MARGIN + rng.uniform(30.0, 1890.0)) * SS
        y = (MARGIN + rng.uniform(30.0, 690.0)) * SS
        r = rng.uniform(0.5, 1.5) * SS
        ld.ellipse([x - r, y - r, x + r, y + r],
                   fill=fade(INK if i % 5 else TEAL_MUTE, rng.uniform(0.16, 0.60)))
    return Image.alpha_composite(img.convert("RGBA"), layer)


def build_sphere_shade() -> Image.Image:
    """Volumetric shading plate for the globe.

    This is a *multiplicative* plate: white everywhere, a lit-sphere falloff
    over the globe disc. Compositing it lets the planetary body share the
    scene's single light direction and gives the wireframe real depth.
    """
    w, h = (W + MARGIN * 2) * SS, (H + MARGIN * 2) * SS
    cx, cy = (GLOBE_CX + MARGIN) * SS, (GLOBE_CY + MARGIN) * SS
    r = GLOBE_R * SS
    gx = np.arange(w, dtype=np.float32)[None, :] - cx
    gy = np.arange(h, dtype=np.float32)[:, None] - cy
    dist = np.sqrt(gx * gx + gy * gy)

    nx = np.clip(gx / r, -1.0, 1.0)
    ny = np.clip(-gy / r, -1.0, 1.0)
    nz = np.sqrt(np.clip(1.0 - (gx * gx + gy * gy) / (r * r), 0.0, 1.0))

    lx, ly, lz = -0.50, -0.60, 0.62
    n = math.sqrt(lx * lx + ly * ly + lz * lz)
    lx, ly, lz = lx / n, ly / n, lz / n

    lam = np.clip(nx * lx + ny * ly + nz * lz, 0.0, 1.0)
    body = 0.30 + 0.62 * lam ** 1.25
    rim = (1.0 - nz) ** 3.0

    plate = np.ones((h, w, 3), dtype=np.float32) * 255.0
    edge = np.clip((r - dist) / (1.6 * SS), 0.0, 1.0)      # anti-aliased limb
    for c, gain in enumerate((0.52, 0.86, 1.34)):
        shaded = np.clip(body + rim * gain * 0.20, 0.0, 1.0) * 255.0
        plate[:, :, c] = 255.0 + (shaded - 255.0) * edge
    return Image.fromarray(np.clip(plate, 0, 255).astype(np.uint8), "RGB")


# --------------------------------------------------------------------------
# Layer 05/06 - frame, instruments and typography (baked once, rock steady)
# --------------------------------------------------------------------------
def build_locked_layer() -> Image.Image:
    sh, sw = (H + MARGIN * 2) * SS, (W + MARGIN * 2) * SS
    fg = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(fg, "RGBA")
    ty = Typo(SS)
    ox, oy = MARGIN * SS, MARGIN * SS

    def P(x, y):
        return (ox + x * SS, oy + y * SS)

    def line(x1, y1, x2, y2, color, alpha, width=1.0):
        d.line([P(x1, y1), P(x2, y2)], fill=fade(color, alpha),
               width=max(1, int(round(width * SS))))

    def rect(x1, y1, x2, y2, color, alpha, width=1.0, radius=0.0):
        box = [P(x1, y1), P(x2, y2)]
        if radius:
            d.rounded_rectangle(box, radius=radius * SS, outline=fade(color, alpha),
                                width=max(1, int(round(width * SS))))
        else:
            d.rectangle(box, outline=fade(color, alpha), width=max(1, int(round(width * SS))))

    def fillrect(x1, y1, x2, y2, color, alpha):
        d.rectangle([P(x1, y1), P(x2, y2)], fill=fade(color, alpha))

    def T(x, y, s, font, size, fill, tracking=0.0, align=None, halo=0.0):
        """Draw with a baseline anchor - keeps optical alignment exact.

        A slight halo keeps telemetry legible wherever the wireframe, orbit
        rings or route arcs pass behind it - without a scrim, so no layout
        band is ever visible.
        """
        ty.draw(d, P(x, y), s, font, size, fill, tracking=tracking, align=align,
                anchor="as", halo=halo)

    # --- instrument frame + corner brackets ------------------------------
    rect(INSET, INSET, W - INSET, H - INSET, TEAL_MUTE, 0.15, 1.0)
    br = 30
    for cx_, cy_, dx_, dy_ in ((INSET, INSET, 1, 1), (W - INSET, INSET, -1, 1),
                               (INSET, H - INSET, 1, -1), (W - INSET, H - INSET, -1, -1)):
        line(cx_, cy_, cx_ + dx_ * br, cy_, LAND, 0.55, 1.6)
        line(cx_, cy_, cx_, cy_ + dy_ * br, LAND, 0.55, 1.6)

    # --- header rule + telemetry ticks -----------------------------------
    line(LEFT, RULE_Y, RIGHT, RULE_Y, SLATE, 0.28, 1.0)
    for i in range(57):
        x = LEFT + i * ((RIGHT - LEFT) / 56.0)
        ln = 7 if i % 7 == 0 else (4 if i % 3 == 0 else 2)
        line(x, RULE_Y, x, RULE_Y + ln, SLATE, 0.28 if i % 7 == 0 else 0.15, 1.0)

    T(LEFT, HEADER_BASE, "YASLOGIST / ENGINEERING & DIGITAL PRODUCTS",
      "JetBrainsMono-SemiBold.ttf", 12.5, fade(TEAL_MUTE, 0.92), tracking=1.7)
    T(RIGHT, HEADER_BASE, "PORTFOLIO VIEW / 001", "JetBrainsMono-Regular.ttf", 12.5,
      fade(SLATE, 0.86), tracking=1.7, align="r", halo=1.6)
    T(RIGHT, HEADER_BASE + 20, "SCHEMATIC / NOT LIVE DATA",
      "JetBrainsMono-Regular.ttf", 10.0, fade(AMBER_MUTE, 0.74), tracking=1.5, align="r",
      halo=1.6)

    # --- brand block ------------------------------------------------------
    T(LEFT, MAST_BASE, "YASLOGIST", "Inter-ExtraBold.ttf", 100, fade(INK, 1.0), tracking=3.0)
    T(LEFT, TAG_BASE, "MOVE SMARTER. SEE FURTHER.", "Inter-SemiBold.ttf", 30,
      fade(INK_SOFT, 0.95), tracking=1.2)
    ax1 = LEFT + 168
    for i in range(int(ax1 - LEFT)):
        t = i / (ax1 - LEFT)
        col = mix(LAND, OCEAN, t / 0.5) if t < 0.5 else mix(OCEAN, AIR, (t - 0.5) / 0.5)
        fillrect(LEFT + i, ACCENT_Y, LEFT + i + 1, ACCENT_Y + 3, col, 0.95)

    # --- multimodal workstreams ------------------------------------------
    T(LEFT, SECTION_BASE, "MULTIMODAL WORKSTREAMS", "JetBrainsMono-SemiBold.ttf", 11.0,
      fade(TEAL_MUTE, 0.82), tracking=2.4)
    T(RAIL_X1, SECTION_BASE, "PUBLIC SCOPE", "JetBrainsMono-Regular.ttf", 10.0,
      fade(SLATE, 0.60), tracking=1.8, align="r")

    for idx, (name, desc, accent, dashed) in enumerate(MODES):
        base = LANE_BASE[idx]
        ry = base + RAIL_DY
        T(LEFT, base, name, "JetBrainsMono-SemiBold.ttf", 14, fade(accent, 0.96), tracking=2.0)
        T(146, base, desc, "JetBrainsMono-Regular.ttf", 9.5, fade(SLATE, 0.64), tracking=1.2)

        if dashed:
            x = RAIL_X0
            while x < RAIL_X1:
                line(x, ry, min(x + 9, RAIL_X1), ry, accent, 0.30, 1.4)
                x += 15
        else:
            for i in range(int(RAIL_X1 - RAIL_X0)):
                t = i / (RAIL_X1 - RAIL_X0)
                fillrect(RAIL_X0 + i, ry - 0.5, RAIL_X0 + i + 1, ry + 0.5, accent,
                         0.18 + 0.16 * t)
        for i in range(17):
            x = RAIL_X0 + i * (RAIL_X1 - RAIL_X0) / 16.0
            long = i % 4 == 0
            line(x, ry - (7 if long else 4), x, ry + (7 if long else 4), accent,
                 0.32 if long else 0.17, 1.0)

    # Converging bus: three modalities -> one intelligence layer.
    for idx in range(3):
        _, _, accent, _ = MODES[idx]
        ry = LANE_BASE[idx] + RAIL_DY
        d.line([P(RAIL_X1, ry), P(BUS_X - 12, ry), P(BUS_X, ry + 12)],
               fill=fade(accent, 0.44), width=max(1, int(round(1.4 * SS))), joint="curve")
    line(BUS_X, LANE_BASE[0] + RAIL_DY, BUS_X, BAR_Y0, TEAL_MUTE, 0.32, 1.4)

    # Intelligence bar.
    fillrect(LEFT, BAR_Y0, BUS_X, BAR_Y1, (14, 42, 52), 0.70)
    rect(LEFT, BAR_Y0, BUS_X, BAR_Y1, TEAL_MUTE, 0.50, 1.0, radius=3)
    for i in range(int(BUS_X - LEFT)):
        t = i / (BUS_X - LEFT)
        col = mix(LAND, OCEAN, t / 0.5) if t < 0.5 else mix(OCEAN, AIR, (t - 0.5) / 0.5)
        fillrect(LEFT + i, BAR_Y0, LEFT + i + 1, BAR_Y0 + 4, col, 0.90)
    T(LEFT + 20, BAR_BASE, "DATA  /  VISIBILITY  /  INTELLIGENCE",
      "Inter-SemiBold.ttf", 17, fade((185, 235, 232), 0.96), tracking=0.8)
    T(BUS_X - 18, BAR_BASE - 1, "SYSTEMS THAT CONNECT", "JetBrainsMono-Regular.ttf",
      9.5, fade(SLATE, 0.68), tracking=1.3, align="r")

    # --- conduit: converged signal route to the core instrument ----------
    conduit = conduit_path()
    d.line([P(*q) for q in conduit], fill=fade(TEAL_MUTE, 0.26),
           width=max(1, int(round(1.3 * SS))), joint="curve")
    for k in range(0, len(conduit) - 1, 6):
        q = conduit[k]
        line(q[0], q[1] - 3, q[0], q[1] + 3, TEAL_MUTE, 0.20, 1.0)
    end = conduit[-1]
    d.ellipse([P(end[0] - 4, end[1] - 4), P(end[0] + 4, end[1] + 4)],
              outline=fade(LAND, 0.62), width=max(1, int(round(1.3 * SS))))

    # --- optical finishing on the core instrument ------------------------
    # A key-light pool inside the disc and a faint anamorphic streak. Both
    # live in the locked layer: they read as lens character and cost nothing
    # per frame.
    inner = Image.new("L", ((W + MARGIN * 2) * SS, (H + MARGIN * 2) * SS), 0)
    idr = ImageDraw.Draw(inner)
    for i in range(30):
        t = i / 30.0
        rr = GLOBE_R * (1.42 - 0.42 * t)
        idr.ellipse([P(GLOBE_CX - rr, GLOBE_CY - rr), P(GLOBE_CX + rr, GLOBE_CY + rr)],
                    fill=int(26 * (t ** 2.1)))
    halo_plate = Image.new("RGB", fg.size, (44, 132, 158))
    fg.paste(halo_plate, (0, 0), inner)
    for i in range(70):
        t = i / 70.0
        hw = 150.0 + 330.0 * t
        a = (1.0 - t) ** 2.4 * 0.20
        d.line([P(GLOBE_CX - hw, GLOBE_CY), P(GLOBE_CX + hw, GLOBE_CY)],
               fill=fade((120, 220, 226), a), width=max(1, int(round(2.2 * SS))))

    # --- bearing ring: the instrument the globe is mounted in ------------
    bcd = P(GLOBE_CX, GLOBE_CY)
    for i in range(180):
        a = math.radians(i * 2.0 - 90.0)
        long = i % 45 == 0
        med = i % 15 == 0
        r0 = BEARING_R
        r1 = r0 - (13 if long else (8 if med else 4))
        col = LAND if long else TEAL_MUTE
        d.line([(bcd[0] + math.cos(a) * r0 * SS, bcd[1] + math.sin(a) * r0 * SS),
                (bcd[0] + math.cos(a) * r1 * SS, bcd[1] + math.sin(a) * r1 * SS)],
               fill=fade(col, 0.42 if long else (0.22 if med else 0.11)),
               width=max(1, int(round(1.0 * SS))))
    for ang, lab in ((90, "090"), (270, "270")):
        a = math.radians(ang - 90.0)
        bx = GLOBE_CX + math.cos(a) * 291.0
        by = GLOBE_CY + math.sin(a) * 291.0
        ty.draw(d, P(bx, by + 3), lab, "JetBrainsMono-Regular.ttf", 9.0,
                fade(SLATE, 0.55), tracking=1.2, align="c", anchor="as")

    # --- footers ----------------------------------------------------------
    T(LEFT, FOOT_BASE_1, "CAIRO, EGYPT   -   PUBLIC PORTFOLIO   -   INDEPENDENT PRODUCTS",
      "JetBrainsMono-Regular.ttf", 10.5, fade(TEAL_MUTE, 0.76), tracking=1.6, halo=1.7)
    T(LEFT, FOOT_BASE_2, "GITHUB.COM/YASLOGIST   -   YASLOGIST.COM",
      "JetBrainsMono-Regular.ttf", 10.5, fade(SLATE, 0.56), tracking=1.6, halo=1.7)
    T(RIGHT, FOOT_BASE_1, "ROUTES: ILLUSTRATIVE GATEWAY SCHEMATIC",
      "JetBrainsMono-Regular.ttf", 10.5, fade(AMBER_MUTE, 0.78), tracking=1.6, align="r",
      halo=1.7)
    T(RIGHT, FOOT_BASE_2, "ORTHOGRAPHIC PROJECTION   -   ORIGIN CAI 30.0N 31.2E",
      "JetBrainsMono-Regular.ttf", 10.5, fade(SLATE, 0.56), tracking=1.6, align="r",
      halo=1.7)

    return fg


def conduit_path(steps=90):
    """Converged-signal route: bar -> bearing ring, joining the core limbus."""
    pts = []
    for i in range(int(steps * 0.42)):
        s = i / (steps * 0.42)
        pts.append((BUS_X + (1030.0 - BUS_X) * s, BAR_BASE - 8.0))
    for i in range(steps):
        s = i / (steps - 1)
        pts.append(bezier3((1030.0, BAR_BASE - 8.0), (1128.0, BAR_BASE - 8.0),
                           (1174.0, BAR_BASE - 24.0), (1198.0, BAR_BASE - 46.0), s))
    return pts


def build_core_mark(radius: float = 112.0) -> Image.Image:
    """The official circular YL mark.

    The two glyph paths are the repository's own logo geometry
    (assets/readme/yaslogist-mark.svg, viewBox 0 0 512 512) - preserved,
    not redrawn.
    """
    sh, sw = (H + MARGIN * 2) * SS, (W + MARGIN * 2) * SS
    layer = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer, "RGBA")
    scale = radius / 238.0
    cx, cy = (MARGIN + GLOBE_CX) * SS, (MARGIN + GLOBE_CY) * SS
    r = radius * SS

    def pts(path):
        return [(cx + (x - 256) * scale * SS, cy + (y - 256) * scale * SS) for x, y in path]

    Y_PATH = [(98, 126), (132, 98), (218, 213), (305, 98), (342, 126), (244, 253),
              (243, 413), (195, 413), (195, 258)]
    L_PATH = [(344, 138), (344, 357), (440, 357), (440, 371), (417, 395), (297, 395), (297, 204)]

    # Housing disc with a soft interior gradient, then rim, then glyphs.
    housing = Image.new("RGB", (int(r * 2) + 2, int(r * 2) + 2), (0, 0, 0))
    hd = ImageDraw.Draw(housing)
    hd.ellipse([0, 0, housing.width - 1, housing.height - 1], fill=(2, 6, 10))
    top = Image.new("L", housing.size, 0)
    ImageDraw.Draw(top).ellipse([0, -(housing.height), housing.width, housing.height],
                                fill=64)
    housing = Image.composite(Image.new("RGB", housing.size, (16, 40, 54)), housing,
                              top.filter(ImageFilter.GaussianBlur(housing.width * 0.16)))
    mask = Image.new("L", housing.size, 0)
    ImageDraw.Draw(mask).ellipse([0, 0, housing.width - 1, housing.height - 1], fill=255)
    layer.paste(housing, (int(cx - r), int(cy - r)), mask)

    d.ellipse([cx - r, cy - r, cx + r, cy + r], outline=fade(INK, 0.95),
              width=max(2, int(round(8 * scale * SS))))
    d.ellipse([cx - r * 1.088, cy - r * 1.088, cx + r * 1.088, cy + r * 1.088],
              outline=fade(TEAL_MUTE, 0.40), width=max(1, int(round(1.2 * SS))))
    d.polygon(pts(Y_PATH), fill=fade(INK, 1.0))
    d.polygon(pts(L_PATH), fill=fade(INK, 1.0))
    return layer


# --------------------------------------------------------------------------
# Layer 02 - the globe (rebuilt per frame)
# --------------------------------------------------------------------------
def _globe_arc(p_latlon, q_latlon, spin, lift=0.30, steps=44):
    out = []
    for i in range(steps + 1):
        s = i / steps
        la = math.radians(p_latlon[0] + (q_latlon[0] - p_latlon[0]) * s)
        lo = math.radians(p_latlon[1] + (q_latlon[1] - p_latlon[1]) * s)
        cl = math.cos(la)
        vx, vy, vz = cl * math.sin(lo), math.sin(la), cl * math.cos(lo)
        n = math.sqrt(vx * vx + vy * vy + vz * vz) or 1.0
        alt = 1.0 + lift * math.sin(math.pi * s)
        vx, vy, vz = vx / n, vy / n, vz / n
        t = math.radians(TILT)
        y2 = vy * math.cos(t) - vz * math.sin(t)
        z2 = vy * math.sin(t) + vz * math.cos(t)
        rot = math.radians(spin)
        rx = vx * math.cos(rot) + vz * math.sin(rot)
        rz = -vx * math.sin(rot) + vz * math.cos(rot)
        out.append((GLOBE_CX + GLOBE_R * alt * rx, GLOBE_CY - GLOBE_R * alt * y2, z2, alt))
    return out


def render_globe(em: Image.Image, p: float, env: float) -> None:
    """Primary visualization: orbitable wireframe globe with the brand's
    home city as the origin of an illustrative gateway network."""
    d = ImageDraw.Draw(em, "RGBA")
    spin = CAMBER + 2.6 * sway(p, 1.0)

    def L(pts, color, alpha, width):
        if len(pts) > 1:
            d.line([(q[0] * SS, q[1] * SS) for q in pts], fill=fade(color, alpha),
                   width=max(1, int(round(width * SS))), joint="curve")

    for lat in (-45, 0, 45):
        front, back = [], []
        for i in range(97):
            x, y, z = project(lat, i * 360.0 / 96.0, spin, GLOBE_CX, GLOBE_CY, GLOBE_R)
            (front if z >= 0 else back).append((x, y, z))
        L(back, TEAL_MUTE, 0.05 + 0.03 * env, 1.0)
        L(front, TEAL_MUTE, (0.18 + 0.12 * env) if lat == 0 else (0.12 + 0.08 * env), 1.0)

    for k in range(8):
        front, back = [], []
        for i in range(73):
            x, y, z = project(-90.0 + i * 180.0 / 72.0, k * 45.0, spin,
                              GLOBE_CX, GLOBE_CY, GLOBE_R)
            (front if z >= 0 else back).append((x, y, z))
        L(back, TEAL_MUTE, 0.05 + 0.03 * env, 1.0)
        L(front, TEAL_MUTE, 0.13 + 0.09 * env, 1.0)

    d.ellipse([(GLOBE_CX - GLOBE_R) * SS, (GLOBE_CY - GLOBE_R) * SS,
               (GLOBE_CX + GLOBE_R) * SS, (GLOBE_CY + GLOBE_R) * SS],
              outline=fade(LAND, 0.34 + 0.18 * env), width=max(1, int(round(1.5 * SS))))
    for rr, al in ((GLOBE_R * 1.05, 0.13), (GLOBE_R * 1.12, 0.07), (GLOBE_R * 1.20, 0.038)):
        d.ellipse([(GLOBE_CX - rr) * SS, (GLOBE_CY - rr) * SS,
                   (GLOBE_CX + rr) * SS, (GLOBE_CY + rr) * SS],
                  outline=fade(LAND, al * (0.55 + 0.5 * env)), width=max(1, int(round(1.0 * SS))))

    # Scanning meridian, faded out at the seam.
    sweep_env = math.sin(math.pi * p) ** 1.4
    if sweep_env > 0.01:
        front, back = [], []
        for i in range(73):
            x, y, z = project(-90.0 + i * 180.0 / 72.0, -180.0 + 360.0 * p, spin,
                              GLOBE_CX, GLOBE_CY, GLOBE_R)
            (front if z >= 0 else back).append((x, y, z))
        L(back, LAND, 0.10 * sweep_env, 2.0)
        L(front, LAND, 0.44 * sweep_env, 2.4)

    for rr, ry, rot0, dcycle, col, alpha, rotating in ORBIT_RINGS:
        rot = rot0 + 360.0 * dcycle * p
        c, s = math.cos(math.radians(rot)), math.sin(math.radians(rot))
        pts = []
        for i in range(181):
            a = TAU * i / 180.0
            ex, ey = rr * math.cos(a), ry * math.sin(a)
            pts.append((GLOBE_CX + ex * c - ey * s, GLOBE_CY + ex * s + ey * c))
        d.line([(x * SS, y * SS) for x, y in pts],
               fill=fade(col, alpha * (0.55 + 0.75 * env)),
               width=max(1, int(round(1.3 * SS))), joint="curve")

        # A single node riding the orbit. Whole cycles per loop, so the mark
        # returns to exactly where it started.
        if not rotating:
            occ = 1
            a = TAU * ((p * occ) % 1.0)
            for k in range(14):
                q = a - k * 0.035
                ex, ey = rr * math.cos(q), ry * math.sin(q)
                px = GLOBE_CX + ex * c - ey * s
                py = GLOBE_CY + ex * s + ey * c
                glow_dot(em, (px, py), 2.2, col,
                         (1.0 - k / 14.0) ** 2 * 0.5 * (0.5 + 0.6 * env))

    # Illustrative gateway network from Cairo.
    for idx, (code, la, lo) in enumerate(GATEWAYS):
        pts = _globe_arc((ORIGIN[1], ORIGIN[2]), (la, lo), spin)
        vis = [q for q in pts if q[2] > -0.12]
        if len(vis) > 1:
            d.line([(x * SS, y * SS) for x, y, _, _ in vis],
                   fill=fade(mix(OCEAN, AIR, 0.35 * (idx % 3)), 0.24 + 0.22 * env),
                   width=max(1, int(round(1.2 * SS))), joint="curve")

        cycles = 3 + (idx % 3)
        s = (p * cycles + idx * 0.137) % 1.0
        i = s * (len(pts) - 1)
        i0 = int(i)
        i1 = min(i0 + 1, len(pts) - 1)
        f = i - i0
        px = pts[i0][0] + (pts[i1][0] - pts[i0][0]) * f
        py = pts[i0][1] + (pts[i1][1] - pts[i0][1]) * f
        if pts[i0][2] > -0.05:
            glow_dot(em, (px, py), 2.5, mix(OCEAN, AIR, 0.5),
                     0.52 * pulse_env(s, 0.07, 0.5) * (0.6 + 0.6 * env))

        x, y, z = project(la, lo, spin, GLOBE_CX, GLOBE_CY, GLOBE_R)
        if z > 0.02:
            node = LAND if idx % 3 == 0 else (OCEAN if idx % 3 == 1 else AIR)
            d.ellipse([(x - 3.2) * SS, (y - 3.2) * SS, (x + 3.2) * SS, (y + 3.2) * SS],
                      outline=fade(node, 0.74), width=max(1, int(round(1.2 * SS))))
            ring = (p + idx * 0.11) % 1.0
            rr = 4.0 + ring * 17.0
            d.ellipse([(x - rr) * SS, (y - rr) * SS, (x + rr) * SS, (y + rr) * SS],
                      outline=fade(node, 0.34 * pulse_env(ring, 0.15, 1.6)),
                      width=max(1, int(round(1.1 * SS))))

    # Origin: Cairo, the brand's home city.
    x, y, z = project(ORIGIN[1], ORIGIN[2], spin, GLOBE_CX, GLOBE_CY, GLOBE_R)
    if z > -0.05:
        alpha = 0.95 if z > 0.05 else 0.45
        lx, ly = x - 92.0, y - 66.0
        d.line([(x * SS, y * SS), ((x - 20) * SS, (y - 20) * SS), (lx * SS, ly * SS)],
               fill=fade(AIR, 0.50 * alpha), width=max(1, int(round(1.1 * SS))), joint="curve")
        d.ellipse([(lx - 3.0) * SS, (ly - 3.0) * SS, (lx + 3.0) * SS, (ly + 3.0) * SS],
                  fill=fade(AIR, 0.92 * alpha))
        glow_dot(em, (x, y), 4.0, AIR, 0.82 * alpha)
        ring = (p * 2.0) % 1.0
        rr = 6.0 + ring * 26.0
        d.ellipse([(x - rr) * SS, (y - rr) * SS, (x + rr) * SS, (y + rr) * SS],
                  outline=fade(AIR, 0.36 * pulse_env(ring, 0.14, 1.5) * alpha),
                  width=max(1, int(round(1.3 * SS))))
        ty = Typo(SS)
        ty.draw(d, ((lx - 9) * SS, (ly - 2) * SS), ORIGIN[0],
                "JetBrainsMono-SemiBold.ttf", 12.5, fade(AIR, 0.95 * alpha),
                tracking=1.9, align="r", anchor="as")
        ty.draw(d, ((lx - 9) * SS, (ly + 16) * SS), "30.0N 31.2E",
                "JetBrainsMono-Regular.ttf", 10.0, fade(AIR, 0.68 * alpha),
                tracking=1.3, align="r", anchor="as")


# --------------------------------------------------------------------------
# Layers 03 / 06 - kinetic geometry
# --------------------------------------------------------------------------
def render_motion(em: Image.Image, p: float, env: float) -> None:
    d = ImageDraw.Draw(em, "RGBA")

    # Lane pulses: one light travelling each modal rail.
    for idx, (name, desc, accent, dashed) in enumerate(MODES):
        ry = LANE_BASE[idx] + RAIL_DY
        s = (p * (2 if dashed else 3) + idx * 0.29) % 1.0
        x = RAIL_X0 + (RAIL_X1 - RAIL_X0) * s
        head = (smoothstep(min(1.0, s / 0.07)) * smoothstep(min(1.0, (1.0 - s) / 0.07))
                * (0.55 + 0.45 * math.sin(math.pi * s)))
        for k in range(26):
            t = k / 26.0
            xa = x - t * 74.0
            if xa < RAIL_X0:
                break
            d.line([(xa * SS, ry * SS), ((xa + 3.4) * SS, ry * SS)],
                   fill=fade(accent, 0.34 * head * (1.0 - t) ** 1.8),
                   width=max(1, int(round(2.2 * SS))))
        glow_dot(em, (x, ry), 3.0, accent, 0.82 * head * (0.6 + 0.5 * env))

    # Converged signal: bar -> bearing ring, four packets per loop.
    conduit = conduit_path()
    total = len(conduit) - 1
    for k in range(4):
        s = (p * 2.0 + k / 4.0) % 1.0
        i = s * total
        i0 = int(i)
        i1 = min(i0 + 1, total)
        f = i - i0
        px = conduit[i0][0] + (conduit[i1][0] - conduit[i0][0]) * f
        py = conduit[i0][1] + (conduit[i1][1] - conduit[i0][1]) * f
        glow_dot(em, (px, py), 2.4, mix(LAND, OCEAN, s),
                 0.60 * pulse_env(s, 0.08, 0.55))

    # Brand core: four emanations per loop, each perfectly periodic.
    for k in range(4):
        ring = (p + k / 4.0) % 1.0
        rr = 118.0 + ring * 156.0
        d.ellipse([(GLOBE_CX - rr) * SS, (GLOBE_CY - rr) * SS,
                   (GLOBE_CX + rr) * SS, (GLOBE_CY + rr) * SS],
                  outline=fade(LAND, 0.30 * pulse_env(ring, 0.12, 1.7)
                               * (0.55 + 0.6 * env)),
                  width=max(1, int(round((2.2 - ring) * SS))))

    # Drifting data motes over the schematic field.
    rng = np.random.default_rng(7715)
    for i in range(46):
        x0 = rng.uniform(900.0, 1830.0)
        span = rng.uniform(300.0, 560.0)
        phase = rng.uniform(0.0, 1.0)
        cyc = int(rng.choice([1, 2]))
        s = (p * cyc + phase) % 1.0
        y = 700.0 - span * s
        x = x0 + 16.0 * sway(p, cyc, phase)
        if (x - GLOBE_CX) ** 2 + (y - GLOBE_CY) ** 2 < 150.0 ** 2:
            continue
        a = math.sin(math.pi * s) ** 0.7
        col = LAND if i % 3 == 0 else (OCEAN if i % 3 == 1 else AIR)
        d.ellipse([(x - 1.1) * SS, (y - 1.1) * SS, (x + 1.1) * SS, (y + 1.1) * SS],
                  fill=fade(col, 0.32 * a * (0.5 + 0.7 * env)))


def render_stars(em: Image.Image, p: float, offset=(0.0, 0.0)) -> None:
    """A small minority of the field twinkles.

    The dense, constant majority lives in the locked background plate. Only
    these few animate, because every blinking point is amortised across a
    wide bloom radius - a cheap effect became the most expensive one in the
    frame. Whole-cycle sine frequencies keep the loop seamless.
    """
    d = ImageDraw.Draw(em, "RGBA")
    rng = np.random.default_rng(31477)
    ox, oy = offset
    for i in range(22):
        x = rng.uniform(30.0, 1890.0) + ox * 1.35
        y = rng.uniform(30.0, 690.0) + oy * 1.35
        r = rng.uniform(0.5, 1.5)
        a = 0.30 + 0.13 * (0.5 + 0.5 * sway(p, int(rng.integers(1, 4)), rng.uniform(0.0, 1.0)))
        if i % 11 == 0:
            a *= 1.8
        d.ellipse([(x - r) * SS, (y - r) * SS, (x + r) * SS, (y + r) * SS],
                  fill=fade(INK if i % 5 else TEAL_MUTE, min(0.85, a)))


SWEEP_P0, SWEEP_P1 = 0.045, 0.195   # the pass occupies ~15% of the loop


def render_sweep(em: Image.Image, p: float, env: float) -> None:
    """Cinematic light pass: one shaft crosses the frame per loop.

    Deliberately windowed. A shaft that travels the entire loop displaces a
    full-height band on every frame, which alone tripled the animation's
    encoded size; keeping it inside a short window preserves the move and
    leaves the rest of the loop clean.
    """
    if not (SWEEP_P0 <= p <= SWEEP_P1):
        return
    d = ImageDraw.Draw(em, "RGBA")
    t0 = (p - SWEEP_P0) / (SWEEP_P1 - SWEEP_P0)
    cx = -320.0 + 2500.0 * ease_in_out_sine(t0)
    band = 104.0
    x0 = max(0, int((cx - band) * SS))
    x1 = min(em.width, int((cx + band) * SS))
    for x in range(x0, x1):
        t = (x / SS - cx) / band
        a = math.exp(-(t * t) * 3.6) * 0.10 * (0.45 + 0.75 * env)
        d.line([(x, 0), (x, em.height)],
               fill=fade(mix(TEAL_MUTE, LAND, 0.4), a), width=1)


# --------------------------------------------------------------------------
# Compositing
# --------------------------------------------------------------------------
def _bloom(em2x: Image.Image, gain: float = 1.0) -> Image.Image:
    """Luminous bleed from the emissive pass, computed at quarter scale.

    Glow is low-frequency, so evaluating it small is visually identical and
    keeps a 200-frame render tractable.
    """
    small = em2x.resize((W // 2, H // 2), Image.BOX)
    wide = np.asarray(small.filter(ImageFilter.GaussianBlur(9.0)), dtype=np.float32)
    tight = np.asarray(small.filter(ImageFilter.GaussianBlur(2.4)), dtype=np.float32)
    a = np.clip((wide * 0.42 + tight * 0.58) * gain, 0.0, 255.0).astype(np.uint8)
    return Image.fromarray(a, "RGB").resize((W, H), Image.BILINEAR)


def _shift(im2x: Image.Image, dx: float, dy: float) -> Image.Image:
    """Translate a 2x emissive canvas by whole supersampled pixels."""
    ox, oy = int(round(dx * SS)), int(round(dy * SS))
    if ox == 0 and oy == 0:
        return im2x
    out = Image.new("RGB", im2x.size, (0, 0, 0))
    out.paste(im2x, (ox, oy))
    return out


def _crop_padded(padded: Image.Image, dx: float, dy: float) -> Image.Image:
    ox = MARGIN * SS + int(round(dx * SS))
    oy = MARGIN * SS + int(round(dy * SS))
    return padded.crop((ox, oy, ox + W * SS, oy + H * SS))


def camera(p: float) -> dict:
    """Bounded camera.

    The atmosphere plate is deliberately locked: panning it would displace
    every pixel of the largest layer each frame, which destroys GIF
    frame-differencing (and with it, the file size). Depth is carried by the
    planetary body and its orbital field drifting against the static
    background instead - the same parallax, a fraction of the payload.
    """
    return {"bg": (0.0, 0.0),
            "globe": (1.9 * sway(p), -1.2 * sway(p, 1.0, 0.25))}


_GRAIN = None


def _static_grain(shape) -> np.ndarray:
    """Temporally constant grain: anti-banding that compression can ignore."""
    global _GRAIN
    if _GRAIN is None or _GRAIN.shape != (shape[0], shape[1], 1):
        rng = np.random.default_rng(20260111)
        _GRAIN = (rng.normal(0.0, 0.9, size=(shape[0], shape[1], 1))
                  .astype(np.float32))
    return _GRAIN


def _grade(view: Image.Image, env: float, *, poster: bool = False) -> Image.Image:
    a = np.asarray(view, dtype=np.float32)
    h, w = a.shape[:2]
    gx = np.linspace(-1.0, 1.0, w, dtype=np.float32)[None, :]
    gy = np.linspace(-1.0, 1.0, h, dtype=np.float32)[:, None]
    r = np.sqrt(gx * gx * 0.92 + gy * gy)
    a *= np.clip(1.0 - 0.34 * np.clip(r - 0.28, 0.0, None) ** 1.7, 0.0, 1.0)[:, :, None]
    lum = a.mean(axis=2, keepdims=True) / 255.0
    shadow = 1.0 - lum
    a[:, :, 0:1] += shadow * 3.6
    a[:, :, 1:2] += shadow * 3.0
    a[:, :, 2:3] += shadow * 5.6
    a[:, :, 0:1] += lum * 2.4
    a[:, :, 2:3] -= lum * 1.2
    if poster:
        a *= 1.03
    # Grain is shade-weighted: it is only needed where the gradients are
    # darkest and banding is most visible. Keeping the bright letterforms
    # clean matters more than anti-banding in the highlights, and the palette
    # then has far less dithering to reproduce across the wordmark.
    a += _static_grain(a.shape) * np.clip(1.15 - lum, 0.0, 1.0)
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


class Scene:
    """Pre-rendered static plates + the per-frame compositor."""

    def __init__(self):
        self.typo = Typo(SS)
        self.bg = build_background()
        self.shade = build_sphere_shade()
        fg = build_locked_layer()
        fg = Image.alpha_composite(fg, build_core_mark())
        # The locked layer is authored at 2x for crispness, then held at 1x so
        # typography is never resampled between frames.
        self.fg1x = fg.resize((W, H), Image.LANCZOS)

    def frame(self, p: float, *, sweep: bool = True, bloom_gain: float = 1.0,
              poster: bool = False) -> Image.Image:
        env = ensemble(p)
        cam = camera(p)

        # 1. atmosphere (parallax: background)
        view = _crop_padded(self.bg, *cam["bg"]).convert("RGB").resize(
            (W, H), Image.LANCZOS)

        # 2. planetary body shading (parallax: globe)
        shade = _crop_padded(self.shade, *cam["globe"]).resize((W, H), Image.LANCZOS)
        view = ImageChops.multiply(view, shade)

        # 3. far field + wireframe globe, emissive
        em_back = Image.new("RGB", (W * SS, H * SS), (0, 0, 0))
        render_stars(em_back, p, offset=cam["bg"])
        globe = Image.new("RGB", (W * SS, H * SS), (0, 0, 0))
        render_globe(globe, p, env)
        em_back = ImageChops.add(em_back, _shift(globe, *cam["globe"]))
        view = ImageChops.add(view, em_back.resize((W, H), Image.BOX))
        view = ImageChops.add(view, _bloom(em_back, bloom_gain * 0.62))

        # 4. locked instrument plate: frame, telemetry, brand mark
        view = Image.alpha_composite(view.convert("RGBA"), self.fg1x).convert("RGB")

        # 5. signal traffic, light pass, brand pulses - in front of the UI
        em_front = Image.new("RGB", (W * SS, H * SS), (0, 0, 0))
        render_motion(em_front, p, env)
        if sweep:
            render_sweep(em_front, p, env)
        view = ImageChops.add(view, em_front.resize((W, H), Image.BOX))
        view = ImageChops.add(view, _bloom(em_front, bloom_gain))

        return _grade(view, env, poster=poster)

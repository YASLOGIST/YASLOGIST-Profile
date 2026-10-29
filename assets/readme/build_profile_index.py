#!/usr/bin/env python3
"""Build and inspect the animated portfolio index for the profile README.

    python3 assets/readme/build_profile_index.py
    python3 assets/readme/build_profile_index.py --check

The index is a schematic of this README's navigation, not a running system or
live activity. The only drawing dependency is Pillow. The typefaces and the
YL mark geometry are read from the existing assets in this directory. Output
is written next to this script; no network access or external encoder is used.
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

from PIL import Image, ImageChops, ImageDraw, ImageFont, ImageSequence, ImageStat, __version__ as PILLOW_VERSION

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from mark import load_mark  # noqa: E402

W, H = 1920, 720
SCALE = 2  # Supersample the fixed artwork, not all 150 animation frames.
FRAMES = 150
DELAY_MS = 60
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

# Each row is an actual group in the README. The named projects are examples
# in that group, not a claim that the linked repositories share a runtime.
ROWS = (
    ("01", "MULTIMODAL WORKSTREAMS", "AIR  /  OCEAN  /  LOGISDATA  /  INTELLIGENCE",
     (118, 214, 196), 158, 994),
    ("02", "INDEPENDENT PRODUCTS", "URLIFE  /  SOUNDVIS  /  VIP MOTORS  /  YAS STORE",
     (232, 184, 129), 298, 1008),
    ("03", "COMPUTATIONAL LABS", "3D-CONTAINERS  /  ORBITAL EARTH",
     (148, 189, 216), 438, 1022),
)
SPINE_X = 944
ROW_CENTERS = (220, 360, 500)


def font(name: str, size: float) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(str(FONT_DIR / name), round(size * SCALE))


def coords(points):
    return [(round(x * SCALE), round(y * SCALE)) for x, y in points]


def box(x0, y0, x1, y1):
    return (round(x0 * SCALE), round(y0 * SCALE),
            round(x1 * SCALE), round(y1 * SCALE))


def draw_text(draw, xy, text, face, size, fill, *, tracking=0, anchor="lt"):
    """Draw consistently spaced, supersampled text without reshaping glyphs."""
    f = font(face, size)
    x, y = xy
    if not tracking:
        draw.text((round(x * SCALE), round(y * SCALE)), text, font=f, fill=fill,
                  anchor=anchor)
        return
    for char in text:
        draw.text((round(x * SCALE), round(y * SCALE)), char, font=f, fill=fill,
                  anchor=anchor)
        x += f.getlength(char) / SCALE + tracking


def draw_mark(draw, cx: float, cy: float, radius: float) -> None:
    """Render the repository's SVG master uniformly, using its original colours."""
    geometry = load_mark()
    mark = geometry.scaled(radius)
    # Pillow draws ellipse strokes inward; expand the outside by half a stroke
    # to match the centred SVG circle stroke.
    half_stroke = mark.stroke_width / 2
    draw.ellipse(box(cx - radius - half_stroke, cy - radius - half_stroke,
                     cx + radius + half_stroke, cy + radius + half_stroke),
                 fill=(2, 6, 9), outline=(242, 246, 246),
                 width=max(1, round(mark.stroke_width * SCALE)))
    for i in range(len(geometry.polygons)):
        draw.polygon(coords([(cx + x, cy + y) for x, y in mark.polygon(i)]),
                     fill=(242, 246, 246))


def build_static() -> Image.Image:
    """Draw the permanently legible typography and the three index leaves."""
    # A flat ink field avoids GIF palette banding. The folio silhouettes add
    # depth; there is no noise, particle field or pseudo-telemetry.
    im = Image.new("RGB", (W * SCALE, H * SCALE), (8, 19, 25))
    d = ImageDraw.Draw(im, "RGBA")
    # Offset folio silhouettes give the index physical depth; they do not
    # represent software connections between the projects.
    d.polygon(coords([(860, 93), (1854, 93), (1854, 616), (1150, 616)]),
              fill=(20, 42, 46, 55))
    d.polygon(coords([(1500, 94), (1854, 94), (1854, 422)]),
              fill=(53, 96, 92, 18))

    # Quiet cropped corners and a header rule keep the plate framed at README
    # width without enclosing it in an ornamental dashboard.
    d.line(coords([(56, 85), (56, 46), (95, 46)]), fill=(92, 164, 151, 170), width=2 * SCALE)
    d.line(coords([(1825, 46), (1864, 46), (1864, 85)]), fill=(92, 164, 151, 170), width=2 * SCALE)
    d.line(coords([(56, 635), (56, 674), (95, 674)]), fill=(92, 164, 151, 170), width=2 * SCALE)
    d.line(coords([(1825, 674), (1864, 674), (1864, 635)]), fill=(92, 164, 151, 170), width=2 * SCALE)
    d.line(coords([(104, 103), (1816, 103)]), fill=(110, 161, 155, 68), width=SCALE)

    draw_text(d, (106, 66), "YASLOGIST  /  ENGINEERING & DIGITAL PRODUCTS",
              "JetBrainsMono-SemiBold.ttf", 19, (140, 197, 186, 255), tracking=1.2)
    draw_text(d, (1432, 66), "A CURATED PUBLIC INDEX",
              "JetBrainsMono-Regular.ttf", 19, (151, 177, 175, 255), tracking=0.8)

    draw_text(d, (105, 154), "YASLOGIST", "Inter-ExtraBold.ttf", 116,
              (242, 245, 239, 255))
    draw_text(d, (105, 272), "PROFILE", "Inter-ExtraBold.ttf", 116,
              (226, 235, 227, 255))
    d.line(coords([(108, 407), (242, 407)]), fill=(113, 210, 191, 255), width=4 * SCALE)
    d.line(coords([(242, 407), (292, 407)]), fill=(224, 174, 119, 255), width=4 * SCALE)
    draw_text(d, (106, 437), "One index. Many independent", "Inter-Regular.ttf", 34,
              (207, 222, 214, 255))
    draw_text(d, (106, 480), "projects, products and ideas.", "Inter-Regular.ttf", 34,
              (207, 222, 214, 255))

    # The mark's shape comes directly from the checked-in SVG. The adjacent
    # wordmark stays fully typeset and is not replaced by an invented logo.
    d.line(coords([(106, 569), (780, 569)]), fill=(108, 160, 152, 70), width=SCALE)
    draw_mark(d, 132, 618, 25)
    draw_text(d, (181, 599), "YASLOGIST  /  CAIRO, EGYPT",
              "JetBrainsMono-SemiBold.ttf", 18, (183, 209, 201, 255), tracking=0.6)
    draw_text(d, (181, 629), "YASLOGIST.COM", "JetBrainsMono-Regular.ttf", 18,
              (119, 191, 178, 255), tracking=0.8)

    # The spine is the portfolio index, with one branch per README section.
    d.line(coords([(814, 360), (SPINE_X, 360)]), fill=(87, 147, 139, 135), width=2 * SCALE)
    d.ellipse(box(805, 351, 823, 369), outline=(152, 205, 191, 220), width=2 * SCALE)
    d.line(coords([(SPINE_X, ROW_CENTERS[0]), (SPINE_X, ROW_CENTERS[-1])]),
           fill=(82, 148, 139, 145), width=2 * SCALE)
    draw_text(d, (997, 120), "THE WORK  /  THREE PATHS",
              "JetBrainsMono-SemiBold.ttf", 19, (152, 202, 190, 255), tracking=1.0)

    for (number, title, projects, accent, top, left), cy in zip(ROWS, ROW_CENTERS):
        right = 1842
        # Three staggered, cut-corner leaves are a physical index metaphor.
        polygon = [(left, top), (right - 52, top), (right, top + 24),
                   (right, top + 110), (left, top + 110)]
        d.polygon(coords(polygon), fill=(23, 47, 51, 225))
        d.line(coords(polygon + [polygon[0]]), fill=(*accent, 75), width=SCALE)
        d.line(coords([(right - 52, top), (right - 52, top + 24),
                       (right, top + 24)]), fill=(*accent, 65), width=SCALE)
        d.line(coords([(SPINE_X, cy), (left, cy)]), fill=(*accent, 125), width=2 * SCALE)
        d.ellipse(box(SPINE_X - 5, cy - 5, SPINE_X + 5, cy + 5),
                  fill=(9, 22, 26, 255), outline=(*accent, 190), width=2 * SCALE)
        draw_text(d, (left + 20, top + 29), number, "JetBrainsMono-SemiBold.ttf", 22,
                  (*accent, 255))
        draw_text(d, (1102, top + 23), title, "Inter-SemiBold.ttf", 41,
                  (235, 243, 235, 255))
        draw_text(d, (1104, top + 77), projects, "JetBrainsMono-Regular.ttf", 23,
                  (179, 207, 200, 255))

    draw_text(d, (997, 594), "NAVIGATION SCHEMATIC  /  NOT LIVE DATA",
              "JetBrainsMono-SemiBold.ttf", 19, (192, 193, 167, 255), tracking=0.6)
    return im.resize((W, H), Image.Resampling.LANCZOS)


def smoothstep(x: float) -> float:
    x = min(1.0, max(0.0, x))
    return x * x * (3 - 2 * x)


def render_frame(base: Image.Image, phase: float, *, poster: bool = False) -> Image.Image:
    """Move a selection along the spine; illuminate the adjacent index leaf."""
    im = base.copy()
    d = ImageDraw.Draw(im, "RGBA")
    # Cosine pacing comes to rest at either end and is periodic at the seam.
    y = ROW_CENTERS[0] + (ROW_CENTERS[-1] - ROW_CENTERS[0]) * (
        0.5 - 0.5 * math.cos(2 * math.pi * phase)
    )
    for (_, _, _, accent, top, left), cy in zip(ROWS, ROW_CENTERS):
        strength = 0.42 if poster else smoothstep(1 - abs(y - cy) / 104)
        if strength <= 0:
            continue
        alpha = round(200 * strength)
        # The selected leaf gently picks up its index colour. Type stays fixed
        # and legible: this is a selection cue, not simulated traffic or status.
        d.polygon([(left, top), (1790, top), (1842, top + 24),
                   (1842, top + 110), (left, top + 110)],
                  fill=(*accent, round(22 * strength)))
        d.line((SPINE_X, cy, left, cy), fill=(*accent, alpha), width=4)
        d.line((left + 3, top + 4, left + 3, top + 106),
               fill=(*accent, alpha), width=5)
        # A ruled edge grows with selection and retracts as the cursor leaves.
        d.line((left, top + 109, left + round(650 * strength), top + 109),
               fill=(*accent, alpha), width=4)
        d.polygon([(left - 3, cy - 8), (left + 10, cy), (left - 3, cy + 8)],
                  fill=(*accent, alpha))
    if poster:
        # The still shows all three branches, rather than freezing the artwork
        # on a single destination or leaving its meaning dependent on motion.
        d.ellipse((SPINE_X - 6, 354, SPINE_X + 6, 366),
                  fill=(222, 239, 229, 255))
    else:
        # A small two-tone selector, no glow, flashing or random movement.
        d.ellipse((SPINE_X - 10, y - 10, SPINE_X + 10, y + 10),
                  fill=(121, 209, 190, 55), outline=(156, 227, 207, 180), width=1)
        d.ellipse((SPINE_X - 4, y - 4, SPINE_X + 4, y + 4),
                  fill=(234, 248, 236, 255))
    return im


def make_palette(base: Image.Image) -> Image.Image:
    """One palette for the loop keeps all fixed typography stable."""
    thumb = (W // 4, H // 4)
    samples = Image.new("RGB", (thumb[0] * 3, thumb[1] * 2))
    for index in range(6):
        sample = render_frame(base, index / 6).resize(thumb, Image.Resampling.LANCZOS)
        samples.paste(sample, ((index % 3) * thumb[0], (index // 3) * thumb[1]))
    return samples.quantize(colors=256, method=Image.Quantize.MAXCOVERAGE,
                            dither=Image.Dither.NONE)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def provenance() -> dict:
    """Record source and output hashes; renderer versions are informational."""
    return {
        "generator": str(Path(__file__).resolve().relative_to(ROOT)),
        "inputs": {str(path.relative_to(ROOT)): sha256(path) for path in INPUTS},
        "artwork": {path.name: {"bytes": path.stat().st_size, "sha256": sha256(path)}
                    for path in (GIF, POSTER)},
        "canvas": [W, H],
        "duration_ms": FRAMES * DELAY_MS,
        "renderer": {"pillow": PILLOW_VERSION},
        "note": "Hashes detect stale files; rasterization can vary across Pillow/FreeType versions.",
    }


def write_stamp() -> None:
    STAMP.write_text(json.dumps(provenance(), indent=2, sort_keys=True) + "\n", encoding="utf-8")


def check_stamp() -> None:
    stamp = json.loads(STAMP.read_text(encoding="utf-8"))
    current = provenance()
    for key in ("generator", "inputs", "artwork", "canvas", "duration_ms"):
        if stamp.get(key) != current[key]:
            raise ValueError(f"Build stamp mismatch in {key}; rebuild both profile-index assets")


def build() -> None:
    base = build_static()
    render_frame(base, 0, poster=True).save(POSTER, optimize=True)
    palette = make_palette(base)
    frames = [render_frame(base, i / FRAMES).quantize(palette=palette,
              dither=Image.Dither.NONE) for i in range(FRAMES)]
    frames[0].save(GIF, save_all=True, append_images=frames[1:],
                   duration=DELAY_MS, loop=0, optimize=True, disposal=1,
                   comment=b"YASLOGIST-Profile: schematic portfolio navigation, not live data.")
    write_stamp()
    print(f"Wrote {GIF.name}, {POSTER.name} and {STAMP.name}")
    check()


def difference(a: Image.Image, b: Image.Image) -> tuple[float, float]:
    """Mean luminance change and RGB-exact changed fraction, on decoded frames."""
    delta = ImageChops.difference(a, b)
    red, green, blue = delta.split()
    any_channel = ImageChops.lighter(ImageChops.lighter(red, green), blue)
    changed = 1 - any_channel.histogram()[0] / (W * H)
    return ImageStat.Stat(delta.convert("L")).mean[0], changed


def check() -> None:
    """Inspect the actual encoded files, not assumptions from the generator."""
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
            raise ValueError("The loop boundary changes unusually many pixels")
    print(f"GIF: {W} x {H}, {count} decoded frames, {duration / 1000:.2f} s, "
          f"loop=infinite, {GIF.stat().st_size:,} bytes")
    print(f"Frame delays: {dict(sorted(delays.items()))} ms")
    print(f"Motion: median {median_changed * 100:.3f}% pixels/step; "
          f"peak {peak_changed * 100:.3f}%; seam {seam[1] * 100:.3f}%")
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
        render_frame(build_static(), 0, poster=True).save(POSTER, optimize=True)
        print(f"Wrote {POSTER.name}")
    else:
        build()


if __name__ == "__main__":
    main()

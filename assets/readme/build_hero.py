#!/usr/bin/env python3
"""Rebuild the YASLOGIST README artwork with procedural drawing tools.

Run from any directory with: python3 assets/readme/build_hero.py
Requires ImageMagick's `convert` command and Pillow for optimized GIF encoding.
The script writes only to this folder; neither tool is an application dependency.
"""
from __future__ import annotations

import math
import shutil
import subprocess
import tempfile
from pathlib import Path

OUT = Path(__file__).resolve().parent
W, H = 1920, 720
CX, CY = 1452.0, 358.0
FRAMES, DELAY_CS = 120, 8  # 9.6-second seamless loop at 12.5 frames per second.
TAU = math.tau

# Reconstructed from the supplied YL logo preview. Coordinates are in a 512-square viewBox.
Y_MARK = [(98, 126), (132, 98), (218, 213), (305, 98), (342, 126), (244, 253), (243, 413), (195, 413), (195, 258)]
L_MARK = [(344, 138), (344, 357), (440, 357), (440, 371), (417, 395), (297, 395), (297, 204)]


def path_data(points: list[tuple[float, float]]) -> str:
    return "M " + " L ".join(f"{x:g} {y:g}" for x, y in points)


LOGO_SVG = f'''<svg xmlns="http://www.w3.org/2000/svg" width="512" height="512" viewBox="0 0 512 512" role="img" aria-label="YASLOGIST circular YL mark">
  <title>YASLOGIST YL mark</title>
  <circle cx="256" cy="256" r="238" fill="#020609" stroke="#F2F6F6" stroke-width="16"/>
  <path d="{path_data(Y_MARK)} Z" fill="#F2F6F6"/>
  <path d="{path_data(L_MARK)} Z" fill="#F2F6F6"/>
</svg>
'''


def run(args: list[str]) -> None:
    subprocess.run(args, check=True, stdout=subprocess.DEVNULL)


def f(value: float) -> str:
    return f"{value:.2f}"


def point_on_ellipse(cx: float, cy: float, rx: float, ry: float, rotation: float, angle: float) -> tuple[float, float]:
    x, y = rx * math.cos(angle), ry * math.sin(angle)
    c, s = math.cos(rotation), math.sin(rotation)
    return cx + x * c - y * s, cy + x * s + y * c


def ellipse_path(cx: float, cy: float, rx: float, ry: float, rotation_deg: float = 0.0,
                 start: float = 0.0, end: float = TAU, segments: int = 112) -> str:
    rot = math.radians(rotation_deg)
    points = [point_on_ellipse(cx, cy, rx, ry, rot, start + (end - start) * i / segments)
              for i in range(segments + 1)]
    body = "M " + " L ".join(f"{f(x)},{f(y)}" for x, y in points)
    if abs(end - start - TAU) < 1e-7:
        body += " Z"
    return f"path '{body}'"


def transformed_mark(points: list[tuple[float, float]], scale: float) -> str:
    mapped = [(CX + (x - 256) * scale, CY + (y - 256) * scale) for x, y in points]
    body = "M " + " L ".join(f"{f(x)},{f(y)}" for x, y in mapped) + " Z"
    return f"path '{body}'"


def circle_draw(x: float, y: float, radius: float, fill: str, stroke: str = "none", width: float = 1) -> str:
    return (f"fill '{fill}'; stroke '{stroke}'; stroke-width {width:g}; "
            f"circle {f(x)},{f(y)} {f(x + radius)},{f(y)}")


def line_draw(x1: float, y1: float, x2: float, y2: float, color: str, width: float = 1) -> str:
    return f"fill none; stroke '{color}'; stroke-width {width:g}; line {f(x1)},{f(y1)} {f(x2)},{f(y2)}"


def make_background(tmp: Path) -> Path:
    """Create a quiet, layered midnight field with a restrained orbital atmosphere."""
    initial = tmp / "background-initial.png"
    haze = tmp / "background-haze.png"
    bg = tmp / "background.png"
    run(["convert", "-size", f"{W}x{H}", "gradient:#0A1927-#040B12", "-depth", "8", f"PNG24:{initial}"])

    haze_draw = ";\n".join([
        "fill 'rgba(37, 132, 150, 0.24)'; stroke none; circle 1450,350 1800,350",
        "fill 'rgba(26, 67, 104, 0.18)'; stroke none; circle 1600,365 1940,365",
        "fill 'rgba(153, 96, 55, 0.12)'; stroke none; circle 1450,500 1690,500",
    ])
    run(["convert", "-size", f"{W}x{H}", "xc:none", "-draw", haze_draw,
         "-blur", "0x115", "-depth", "8", f"PNG32:{haze}"])
    run(["convert", str(initial), str(haze), "-compose", "over", "-composite",
         "-depth", "8", f"PNG24:{bg}"])

    # Hairline structure is deliberately concentrated behind the visualization, not the title.
    rules: list[str] = []
    for x in range(960, 1881, 80):
        rules.append(line_draw(x, 140, x, 624, "rgba(83, 139, 158, 0.075)", 1))
    for y in range(160, 625, 56):
        rules.append(line_draw(940, y, 1850, y, "rgba(83, 139, 158, 0.065)", 1))
    # A sparse perspective floor converges into the orbital field.
    for x in (990, 1120, 1260, 1410, 1560, 1720, 1880):
        rules.append(line_draw(1440, 442, x, 624, "rgba(89, 147, 163, 0.075)", 1))
    for y in (495, 526, 557, 588, 619):
        rules.append(line_draw(1000, y, 1852, y, "rgba(89, 147, 163, 0.055)", 1))

    rules.extend([
        line_draw(86, 118, 1834, 118, "rgba(100, 163, 179, 0.33)", 1),
        line_draw(86, 625, 1834, 625, "rgba(100, 163, 179, 0.29)", 1),
        line_draw(928, 137, 928, 607, "rgba(100, 163, 179, 0.13)", 1),
    ])
    particles = [
        (1007, 183, 1.4), (1078, 456, 1.7), (1175, 164, 1.2), (1268, 558, 1.4),
        (1334, 176, 1.3), (1518, 139, 1.7), (1620, 593, 1.3), (1718, 164, 1.5),
        (1813, 430, 1.6), (1768, 570, 1.3), (1046, 302, 1.2), (1847, 233, 1.1),
    ]
    for x, y, r in particles:
        rules.append(circle_draw(x, y, r, "rgba(122, 183, 195, 0.48)"))
    grid_bg = tmp / "background-grid.png"
    run(["convert", str(bg), "-draw", ";\n".join(rules), "-depth", "8", f"PNG24:{grid_bg}"])
    return grid_bg


def add_glow(glow_items: list[str], x: float, y: float, color: str, radius: float = 16.0, opacity: float = 0.72) -> None:
    glow_items.append(circle_draw(x, y, radius, f"rgba({color}, {opacity:.3f})"))


def rgb_from_hex(value: str) -> str:
    raw = value.lstrip("#")
    return ", ".join(str(int(raw[i:i + 2], 16)) for i in (0, 2, 4))


def draw_text(cmd: list[str], x: int, y: int, text: str, size: int, color: str,
              font: str = "DejaVu-Sans-Mono", kerning: float = 0.0) -> None:
    cmd.extend(["-font", font, "-pointsize", str(size), "-kerning", str(kerning),
                "-fill", color, "-stroke", "none", "-draw", f'text {x},{y} "{text}"'])


def render_frame(bg: Path, output: Path, phase: float) -> None:
    angle = TAU * phase
    energy = 0.67 + 0.22 * (0.5 - 0.5 * math.cos(angle))
    camera = 0.0  # Keep the mesh stationary so GIF delta frames stay compact; routes provide the motion.
    glows: list[str] = []
    details: list[str] = []

    # Three illustrative route families orbit a shared engineering mark.
    routes = [
        {"name": "LAND", "color": "74, 218, 199", "rx": 326.0, "ry": 128.0, "rot": -24.0, "offset": 0.45},
        {"name": "OCEAN", "color": "108, 174, 232", "rx": 270.0, "ry": 204.0, "rot": 43.0, "offset": -1.15},
        {"name": "AIR", "color": "244, 176, 116", "rx": 356.0, "ry": 88.0, "rot": 8.0, "offset": 2.35},
    ]
    pulse_positions: list[tuple[float, float, str]] = []
    for route in routes:
        path = ellipse_path(CX, CY, route["rx"], route["ry"], route["rot"], segments=144)
        details.append(f"fill none; stroke 'rgba({route['color']}, 0.30)'; stroke-width 1.45; {path}")
        # A finer, offset companion line gives each corridor a little parallax.
        details.append(f"fill none; stroke 'rgba({route['color']}, 0.105)'; stroke-width 1; "
                       f"{ellipse_path(CX, CY, route['rx'] + 8, route['ry'] + 7, route['rot'], segments=144)}")
        rotation = math.radians(route["rot"])
        theta = angle + route["offset"]
        # A bright moving signal and three progressively dimmer trailing points.
        for tail in range(4):
            px, py = point_on_ellipse(CX, CY, route["rx"], route["ry"], rotation, theta - tail * 0.105)
            pulse_positions.append((px, py, route["color"]))
            radius = (5.2 - tail * 0.85) * energy
            opacity = 0.94 - tail * 0.19
            details.append(circle_draw(px, py, radius, f"rgba({route['color']}, {opacity:.3f})"))
            if tail == 0:
                details.append(circle_draw(px, py, 2.0, "#F3FAF8"))

    # Sphere-like mesh: deliberately abstract, not a geographic or live-tracking map.
    details.append(circle_draw(CX, CY, 242, "rgba(5, 17, 27, 0.47)", "rgba(93, 174, 188, 0.34)", 1.6))
    details.append(circle_draw(CX, CY, 231, "none", "rgba(99, 168, 182, 0.13)", 1.0))
    grid_rot = camera
    for lat in (-0.76, -0.48, -0.22, 0.0, 0.22, 0.48, 0.76):
        dy = lat * 224.0
        rx = math.sqrt(max(0.0, 224.0 * 224.0 - dy * dy))
        ry = 14.0 + 25.0 * (1.0 - abs(lat))
        details.append(f"fill none; stroke 'rgba(100, 177, 190, {0.10 if lat else 0.19:.3f})'; stroke-width 1; "
                       f"{ellipse_path(CX, CY + dy, rx, ry, grid_rot, segments=88)}")
    for rx in (36.0, 78.0, 122.0, 168.0, 211.0):
        details.append(f"fill none; stroke 'rgba(111, 181, 191, 0.12)'; stroke-width 1; "
                       f"{ellipse_path(CX, CY, rx, 226.0, grid_rot, segments=88)}")

    # Fine orbital index marks and one rotating scan vector.
    for i in range(48):
        a = TAU * i / 48.0
        r1 = 258.0
        r2 = r1 + (9.0 if i % 4 == 0 else 4.0)
        x1, y1 = CX + r1 * math.cos(a), CY + r1 * math.sin(a)
        x2, y2 = CX + r2 * math.cos(a), CY + r2 * math.sin(a)
        alpha = 0.24 if i % 4 == 0 else 0.12
        details.append(line_draw(x1, y1, x2, y2, f"rgba(126, 189, 195, {alpha})", 1.2))
    scan_a = angle - math.pi / 2.0
    sx1, sy1 = CX + 162 * math.cos(scan_a), CY + 162 * math.sin(scan_a)
    sx2, sy2 = CX + 238 * math.cos(scan_a), CY + 238 * math.sin(scan_a)
    details.append(line_draw(sx1, sy1, sx2, sy2, f"rgba(91, 230, 208, {0.18 + 0.12 * energy:.3f})", 1.4))
    scan_x, scan_y = CX + 258 * math.cos(scan_a), CY + 258 * math.sin(scan_a)
    add_glow(glows, scan_x, scan_y, "92, 235, 211", 13, 0.58)
    details.append(circle_draw(scan_x, scan_y, 4.4, "#8BEAD9"))

    # The core is a quiet disc so the supplied monogram remains unmistakable over the mesh.
    logo_scale = 0.58
    details.append(circle_draw(CX, CY, 151, "rgba(4, 12, 19, 0.97)", "rgba(128, 181, 191, 0.38)", 1.3))
    ring_alpha = 0.62 + 0.15 * (0.5 + 0.5 * math.sin(angle - 0.7))
    details.append(circle_draw(CX, CY, 138.0, "none", f"rgba(239, 246, 246, {ring_alpha:.3f})", 7.0))
    details.append(circle_draw(CX, CY, 127.0, "none", "rgba(110, 174, 185, 0.19)", 1.0))
    details.append(f"fill '#F2F6F6'; stroke none; {transformed_mark(Y_MARK, logo_scale)}")
    details.append(f"fill '#F2F6F6'; stroke none; {transformed_mark(L_MARK, logo_scale)}")
    # A tiny jewel at 12 o'clock ties the logo to the cyan route family.
    details.append(circle_draw(CX, CY - 143.0, 3.0, "#67D8C8"))

    # Three stable, labeled reference nodes: portfolio categories, not live feed endpoints.
    labels = [
        {"x": 1137, "y": 238, "name": "LAND", "sub": "VISION", "color": "#62D8C7", "dot": (1117, 230), "phase": 0.35},
        {"x": 1703, "y": 246, "name": "OCEAN", "sub": "MARITIME", "color": "#79B8E9", "dot": (1681, 238), "phase": 2.2},
        {"x": 1243, "y": 563, "name": "AIR", "sub": "FREIGHT", "color": "#F0B27A", "dot": (1222, 555), "phase": 4.1},
    ]
    for item in labels:
        pulse = 0.5 + 0.5 * math.sin(angle + item["phase"])
        dx, dy = item["dot"]
        add_glow(glows, dx, dy, rgb_from_hex(item["color"]), 11.0 + pulse * 2.0, 0.48)
        details.append(circle_draw(dx, dy, 7 + pulse * 1.3, "none", item["color"], 1.25))
        details.append(circle_draw(dx, dy, 2.5, item["color"]))
        details.append(line_draw(dx + 10, dy, item["x"] - 8, dy, f"rgba(126, 183, 192, 0.35)", 1))

    # Place diffuse signal blooms beneath the crisp vector work.
    glow_draw = ";\n".join([circle_draw(x, y, 15.0, f"rgba({color}, 0.60)") for x, y, color in pulse_positions] + glows)
    draw_string = ";\n".join(details)
    underlay = output.with_name(output.stem + "-underlay.png")
    cmd = [
        "convert", str(bg),
        "(", "-size", f"{W}x{H}", "xc:none", "-draw", glow_draw, "-blur", "0x16", ")",
        "-compose", "over", "-composite",
        "-draw", draw_string,
        "-depth", "8", "-define", "png:compression-level=6", f"PNG24:{underlay}",
    ]
    run(cmd)

    # Editorial type is kept on the left: legible at GitHub's responsive display size.
    text_cmd: list[str] = ["convert", str(underlay)]
    draw_text(text_cmd, 98, 82, "YASLOGIST  /  ENGINEERING & DIGITAL PRODUCTS", 16, "#8EADB7", kerning=1.3)
    draw_text(text_cmd, 98, 270, "YASLOGIST", 92, "#EEF4F5", "DejaVu-Sans-Bold", kerning=1.4)
    draw_text(text_cmd, 101, 329, "MOVE SMARTER. SEE FURTHER.", 28, "#C4D9DE", "DejaVu-Sans", kerning=0.4)
    draw_text(text_cmd, 101, 411, "LAND  /  OCEAN  /  AIR", 19, "#6ED7C8", "DejaVu-Sans-Mono", kerning=1.4)
    draw_text(text_cmd, 101, 448, "DATA  /  VISIBILITY  /  INTELLIGENCE", 16, "#83A6B0", "DejaVu-Sans-Mono", kerning=0.5)
    draw_text(text_cmd, 101, 560, "CAIRO, EGYPT", 14, "#A7BEC5", "DejaVu-Sans-Mono", kerning=1.0)
    draw_text(text_cmd, 252, 560, "PUBLIC PORTFOLIO", 14, "#6D929E", "DejaVu-Sans-Mono", kerning=0.8)
    draw_text(text_cmd, 101, 598, "ILLUSTRATIVE SYSTEMS + INDEPENDENT PRODUCTS", 13, "#73909B", "DejaVu-Sans-Mono", kerning=0.25)
    draw_text(text_cmd, 1541, 82, "PORTFOLIO VIEW  /  001", 14, "#7E9DA8", "DejaVu-Sans-Mono", kerning=0.8)
    draw_text(text_cmd, 1541, 101, "CONCEPT ROUTES  /  NOT LIVE DATA", 11, "#597782", "DejaVu-Sans-Mono", kerning=0.45)
    for item in labels:
        draw_text(text_cmd, item["x"], item["y"], item["name"], 15, item["color"], "DejaVu-Sans-Bold", kerning=1.1)
        draw_text(text_cmd, item["x"], item["y"] + 19, item["sub"], 10, "#83A3AD", "DejaVu-Sans-Mono", kerning=0.55)
    # Keep the title accent fixed; the orbital system carries the looped motion.
    accent = line_draw(101, 356, 169, 356, "#58DCC8", 2.5)
    text_cmd.extend(["-draw", accent, "-depth", "8", "-define", "png:compression-level=6", f"PNG24:{output}"])
    run(text_cmd)
    underlay.unlink(missing_ok=True)


def make_signature(tmp: Path) -> Path:
    """Create a theme-safe closing tile: the mark owns its dark field."""
    out = OUT / "yaslogist-signature.png"
    base = tmp / "signature-base.png"
    run(["convert", "-size", "1200x190", "gradient:#0A1C2B-#040A11", "-depth", "8", f"PNG24:{base}"])
    d: list[str] = [
        "fill 'rgba(50, 150, 157, 0.16)'; stroke none; circle 112,95 212,95",
        "fill none; stroke 'rgba(99, 171, 183, 0.28)'; stroke-width 1; line 238,30 238,160",
        circle_draw(112, 95, 75, "rgba(4, 12, 19, 0.98)", "rgba(228, 239, 240, 0.86)", 4.5),
        circle_draw(112, 95, 68, "none", "rgba(110, 174, 185, 0.23)", 1),
    ]
    scale = 0.31
    for mark in (Y_MARK, L_MARK):
        pts = [(112 + (x - 256) * scale, 95 + (y - 256) * scale) for x, y in mark]
        data = "M " + " L ".join(f"{f(x)},{f(y)}" for x, y in pts) + " Z"
        d.append(f"fill '#F2F6F6'; stroke none; path '{data}'")
    sign_base = tmp / "signature-art.png"
    run(["convert", str(base), "-draw", ";\n".join(d), "-depth", "8", f"PNG24:{sign_base}"])
    args: list[str] = ["convert", str(sign_base)]
    draw_text(args, 274, 91, "YASLOGIST", 54, "#EEF4F5", "DejaVu-Sans-Bold", kerning=1.7)
    draw_text(args, 278, 127, "MOVE SMARTER. SEE FURTHER.", 18, "#9BC1C7", "DejaVu-Sans", kerning=0.8)
    draw_text(args, 278, 155, "ENGINEERING  /  CAIRO, EGYPT", 12, "#73929C", "DejaVu-Sans-Mono", kerning=0.9)
    draw_text(args, 930, 105, "YASLOGIST.COM", 15, "#68D4C4", "DejaVu-Sans-Mono", kerning=1.4)
    args.extend(["-depth", "8", "-define", "png:compression-level=8", f"PNG24:{out}"])
    run(args)
    return out


def write_palette_and_gif(frames: list[Path], output: Path, delay: int, tmp: Path) -> None:
    """Quantize one frame at a time, then let Pillow optimize the shared-palette loop."""
    try:
        from PIL import Image
    except ImportError as error:
        raise SystemExit("Pillow is required for GIF encoding; install it with `python -m pip install Pillow`.") from error

    with Image.open(frames[len(frames) // 2]) as source:
        palette = source.convert("RGB").quantize(
            colors=256, method=Image.Quantize.MEDIANCUT, dither=Image.Dither.NONE
        )

    indexed_frames = []
    for path in frames:
        with Image.open(path) as source:
            # A fixed palette without error-diffusion keeps static pixels identical frame to frame,
            # allowing Pillow to crop the moving signal deltas instead of encoding the whole canvas.
            indexed = source.convert("RGB").quantize(
                palette=palette, dither=Image.Dither.NONE
            )
        indexed_frames.append(indexed)

    indexed_frames[0].save(
        output,
        format="GIF",
        save_all=True,
        append_images=indexed_frames[1:],
        duration=delay * 10,
        loop=0,
        optimize=True,
        disposal=1,
    )
    for image in indexed_frames:
        image.close()


def make_signal(tmp: Path) -> None:
    """A restrained moving light rail provides a second, lightweight motion layer."""
    w, h, count, delay = 1200, 30, 40, 8
    frames: list[Path] = []
    for i in range(count):
        phase = i / count
        x = 600 + 522 * math.sin(TAU * phase)
        frame = tmp / f"signal-{i:03d}.png"
        line = line_draw(26, 15, 1174, 15, "#547983", 1)
        glow = circle_draw(x, 15, 12, "rgba(72, 219, 198, 0.70)")
        cmd = ["convert", "-size", f"{w}x{h}", "xc:#06121d",
               "(", "-size", f"{w}x{h}", "xc:none", "-draw", glow, "-blur", "0x8", ")",
               "-compose", "over", "-composite",
               "-draw", ";\n".join([
                   line,
                   line_draw(x - 26, 15, x + 26, 15, "#64D8C6", 2.0),
                   circle_draw(x, 15, 3.0, "#E7F8F4"),
                   circle_draw(26, 15, 2.1, "#67D6C5"),
                   circle_draw(1174, 15, 2.1, "#67D6C5"),
               ]), "-depth", "8", f"PNG32:{frame}"]
        run(cmd)
        frames.append(frame)
    write_palette_and_gif(frames, OUT / "yaslogist-signal.gif", delay, tmp)


def main() -> None:
    if not shutil.which("convert"):
        raise SystemExit("ImageMagick `convert` is required to render the README artwork.")
    try:
        import PIL  # noqa: F401
    except ImportError as error:
        raise SystemExit("Pillow is required for GIF encoding; install it with `python -m pip install Pillow`.") from error
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "yaslogist-mark.svg").write_text(LOGO_SVG, encoding="utf-8")
    with tempfile.TemporaryDirectory(prefix="yaslogist-readme-art-") as work:
        tmp = Path(work)
        bg = make_background(tmp)
        frames: list[Path] = []
        for i in range(FRAMES):
            frame = tmp / f"hero-{i:03d}.png"
            render_frame(bg, frame, i / FRAMES)
            frames.append(frame)
            if (i + 1) % 15 == 0:
                print(f"Rendered hero frame {i + 1}/{FRAMES}")
        # The first frame is also the high-resolution static fallback poster.
        run(["convert", str(frames[0]), "-depth", "8", "-define", "png:compression-level=9",
             f"PNG24:{OUT / 'yaslogist-hero.png'}"])
        write_palette_and_gif(frames, OUT / "yaslogist-hero.gif", DELAY_CS, tmp)
        make_signal(tmp)
        make_signature(tmp)

    print("Generated:")
    for name in ("yaslogist-hero.gif", "yaslogist-hero.png", "yaslogist-signal.gif",
                 "yaslogist-mark.svg", "yaslogist-signature.png"):
        path = OUT / name
        print(f"  {path.name}: {path.stat().st_size:,} bytes")


if __name__ == "__main__":
    main()

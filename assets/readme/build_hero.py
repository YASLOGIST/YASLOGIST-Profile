#!/usr/bin/env python3
"""Build the YASLOGIST profile README artwork.

Run from the repository root:

    python3 assets/readme/build_hero.py

Produces, next to this file:

    yaslogist-hero.gif    1920x720, 200 frames, 10.0 s seamless loop
    yaslogist-hero.png    1920x720 static poster (fallback still)

The scene is drawn procedurally by `scene.py` (Pillow + NumPy) - no stock
imagery, no network access, and no JavaScript at display time, so GitHub
renders the motion directly. Brand-mark geometry is read from
`yaslogist-mark.svg` by `mark.py`, so the logo has a single source of truth.

Requirements: Pillow and NumPy only. Fonts are read from `assets/readme/fonts/`,
so the build needs no network access and stays reproducible.

Encoding notes: Pillow's GIF writer already delta-crops unchanged regions and
fills them with transparency. What actually governs the file size on this
scene is how many pixels change per frame, so the art direction was tuned for
motion economy (see `camera()` in `scene.py`) - not the palette alone.

The artwork is a schematic map of the public portfolio. Route lines are
illustrative gateway metaphors and are labelled as such on screen.
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

# Keep the source tree clean: the scene module is imported, never packaged.
sys.dont_write_bytecode = True

import numpy as np
from PIL import Image

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import scene  # noqa: E402
from scene import DELAY_MS, FRAMES, H, W, Scene  # noqa: E402

GIF_OUT = HERE / "yaslogist-hero.gif"
PNG_OUT = HERE / "yaslogist-hero.png"

PALETTE_SAMPLES = 16          # frames averaged into the single global palette
PALETTE_COLORS = 254          # single shared palette; the brand wordmark
                              # needs the full range to stay pristine
POSTERIZE = 1                 # 1 = leave the source alone before mapping
POSTER_P = 0.50               # loop position used for the static poster


def build_palette(frames: list[Image.Image]) -> Image.Image:
    """One global palette for the whole loop.

    A per-frame palette makes flat areas crawl between frames; a single
    shared palette keeps the gradient field stable and compresses better.
    """
    step = max(1, len(frames) // PALETTE_SAMPLES)
    picks = frames[::step][:PALETTE_SAMPLES]
    tw, th = W // 4, H // 4
    cols, rows = 4, (len(picks) + 3) // 4
    sheet = Image.new("RGB", (tw * cols, th * rows), (0, 0, 0))
    for i, f in enumerate(picks):
        sheet.paste(f.resize((tw, th), Image.LANCZOS), ((i % cols) * tw, (i // cols) * th))
    # MAXCOVERAGE, not MEDIANCUT: on this scene it is both smaller and
    # cleaner for the brand wordmark. Its palette ordering also runs similar
    # colours together, which the encoder rewards with long index runs -
    # reseeding or reordering the palette to "protect" brand tones costs
    # roughly 60% more bytes for no measurable gain in the letterforms.
    return sheet.quantize(colors=PALETTE_COLORS, method=Image.MAXCOVERAGE,
                          dither=Image.Dither.NONE)


def _smooth(f: Image.Image) -> Image.Image:
    """Round the source to a coarser tonal grid before palette mapping.

    On a dark, low-contrast scene this leaves the palette to do the real
    colour work while making index runs far more uniform, which is what the
    GIF encoder actually rewards. The poster still is left untouched.
    """
    a = np.asarray(f, dtype=np.int16)
    a = ((a + POSTERIZE // 2) // POSTERIZE) * POSTERIZE
    return Image.fromarray(np.clip(a, 0, 255).astype(np.uint8), "RGB")


def encode_gif(frames: list[Image.Image], palette: Image.Image) -> None:
    quantised = [_smooth(f).quantize(palette=palette, dither=Image.Dither.NONE)
                 for f in frames]
    quantised[0].save(
        GIF_OUT,
        save_all=True,
        append_images=quantised[1:],
        duration=DELAY_MS,
        loop=0,
        optimize=True,
        disposal=1,
        comment=b"YASLOGIST profile hero - schematic portfolio map, not live data.",
    )


def main() -> int:
    t0 = time.time()
    print(f"YASLOGIST hero render - {W}x{H}, {FRAMES} frames, {FRAMES * DELAY_MS / 1000:.1f}s loop")
    sc = Scene()
    print(f"  static layers built in {time.time() - t0:.1f}s")

    frames: list[Image.Image] = []
    for i in range(FRAMES):
        p = i / FRAMES
        frames.append(sc.frame(p))
        if (i + 1) % 20 == 0 or i == FRAMES - 1:
            done = time.time() - t0
            rate = (i + 1) / max(done, 1e-6)
            print(f"  frame {i + 1:>4}/{FRAMES}  {done:6.1f}s  ({rate:.1f} fps)")

    # ---- loop integrity check (frame N must match frame 0) --------------
    a = np.asarray(frames[0].convert("L"), dtype=np.int16)
    b = np.asarray(frames[-1].convert("L"), dtype=np.int16)
    print(f"  loop seam: frame[0] vs frame[{FRAMES - 1}] max|delta| = {np.abs(a - b).max()}")

    # ---- static poster ---------------------------------------------------
    poster = sc.frame(POSTER_P, sweep=False, bloom_gain=1.18, poster=True)
    poster.save(PNG_OUT, optimize=True)

    # ---- GIF -------------------------------------------------------------
    palette = build_palette(frames)
    encode_gif(frames, palette)

    # No ImageMagick post-pass: re-quantising an already-optimal GIF risks
    # damaging the wordmark for a marginal gain. Pillow's writer is the only
    # encoder this build uses.

    for f in (GIF_OUT, PNG_OUT):
        print(f"  wrote {f.name}  {f.stat().st_size / 1024 / 1024:.2f} MB")
    print(f"done in {time.time() - t0:.1f}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

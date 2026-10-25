#!/usr/bin/env python3
"""Verify the committed YASLOGIST profile assets against what the README claims.

The profile has no application runtime: the thing that can actually be wrong is
the *artwork and the links around it*. This script turns the README's
"Verified by inspection" table into something a machine re-checks, so a broken
GIF, a drifted asset path, a palette regression or a desynchronised generator
constant fails loudly instead of quietly degrading the profile.

Run from the repository root:

    python3 tools/verify_assets.py            # full report
    python3 tools/verify_assets.py --quiet    # failures + warnings only
    python3 tools/verify_assets.py --strict   # also fail if Pillow is missing

Exit codes: 0 = every check passed, 1 = a check failed.

Structural checks are pure standard library. The pixel checks (palette
identity, blank frames, loop seam, flicker) need Pillow, because they decode
the GIF; without it they are reported as SKIP rather than silently dropped.
"""
from __future__ import annotations

import argparse
import re
import struct
import sys
from dataclasses import dataclass, field
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
README_DIR = ROOT / "assets" / "readme"
HERO = README_DIR / "yaslogist-hero.gif"
POSTER = README_DIR / "yaslogist-hero.png"
SIGNAL = README_DIR / "yaslogist-signal.gif"
SIGNATURE = README_DIR / "yaslogist-signature.png"
MARK_SVG = README_DIR / "yaslogist-mark.svg"
SCENE = README_DIR / "scene.py"
BUILD_HERO = README_DIR / "build_hero.py"
WORKFLOW = ROOT / ".github" / "workflows" / "verify.yml"

# Regression thresholds derived from the committed artwork. They are not
# aspirational targets: each one is a little looser than the measured value so
# ordinary deterministic noise cannot trip it, while a real regression can.
MIN_FRAME_STD = 5.0          # a blank frame would fall near 0 (measured ~33.5)
MAX_MEAN_STEP = 1.0          # /255 global brightness change per frame (measured 0.54)
MAX_MEDIAN_STEP = 0.8        # /255 per pixel (measured 0.43)
MAX_P95_STEP = 3.5           # /255 per pixel (measured 2.64)
# Re-rendering a committed frame is only byte-exact under the Pillow build that
# produced it (glyph antialiasing comes from FreeType). `build_hero.RENDERER_PIN`
# names that version, so the verifier can tell a genuine drift from a renderer
# difference instead of guessing with a loose tolerance.
MAX_REPRODUCE_DIFF = 0.25         # mean channel error, pinned renderer (measured 0.00)
MAX_REPRODUCE_OUTLIERS = 0.002    # share of pixels off by >8/255, pinned renderer (0.000)
# Fallback when the installed Pillow is not the pinned one: coarser, but still
# catches a scene edit or stale artwork (a 6 px globe change measures 1.52 mean).
MAX_LOOSE_DIFF = 1.0
MAX_LOOSE_P99 = 30.0              # 95th/99th percentile of the 4x-averaged error

ASSET_REF = re.compile(r'(?:src|href)="(\.?/?[^"#][^"]*)"|\]\((\.?/[^)\s]+)\)')
MEDIA_SUFFIXES = {".gif", ".png", ".svg", ".jpg", ".jpeg", ".webp"}

# Earlier hero artwork, drawn in a retired brand identity. It is deliberately
# not shown in the README (the poster carries a "SYSTEMS ONLINE" indicator that
# the current profile would never claim), but it is not this tool's job to
# delete repository content. Excluding it by name keeps the orphan warning
# actionable: any *other* unreferenced media is a real bookkeeping mistake.
LEGACY_MEDIA = frozenset({
    "assets/yaslogist-motion.gif",
    "assets/yaslogist-poster.png",
})


# --------------------------------------------------------------------------
# Reporting
# --------------------------------------------------------------------------
@dataclass
class Report:
    checks: list[tuple[str, str, str]] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def ok(self, name: str, detail: str = "") -> None:
        self.checks.append((name, "PASS", detail))

    def fail(self, name: str, detail: str) -> None:
        self.checks.append((name, "FAIL", detail))

    def skip(self, name: str, detail: str) -> None:
        self.checks.append((name, "SKIP", detail))

    def check(self, name: str, condition: bool, detail: str) -> bool:
        (self.ok if condition else self.fail)(name, detail)
        return condition

    def warn(self, message: str) -> None:
        self.warnings.append(message)

    @property
    def failures(self) -> list[tuple[str, str, str]]:
        return [c for c in self.checks if c[1] == "FAIL"]

    @property
    def skips(self) -> list[tuple[str, str, str]]:
        return [c for c in self.checks if c[1] == "SKIP"]

    def render(self, quiet: bool = False) -> str:
        lines: list[str] = []
        if not quiet:
            width = max((len(c[0]) for c in self.checks), default=10)
            for name, status, detail in self.checks:
                lines.append(f"  {status:<4}  {name:<{width}}  {detail}")
        if quiet:
            for name, _, detail in self.failures:
                lines.append(f"  FAIL  {name}: {detail}")
        for message in self.warnings:
            lines.append(f"  WARN  {message}")
        passed = sum(1 for c in self.checks if c[1] == "PASS")
        lines.append(
            f"\n{passed} passed · {len(self.failures)} failed · "
            f"{len(self.skips)} skipped · {len(self.warnings)} warning(s)"
        )
        return "\n".join(lines)


# --------------------------------------------------------------------------
# README <-> assets
# --------------------------------------------------------------------------
def readme_asset_refs(text: str) -> list[str]:
    """Local asset paths referenced by the README (HTML and Markdown)."""
    refs: list[str] = []
    for html_ref, md_ref in ASSET_REF.findall(text):
        raw = html_ref or md_ref
        if not raw or "://" in raw or raw.startswith(("mailto:", "#")):
            continue
        refs.append(raw.lstrip("./"))
    return refs


def find_orphans(referenced: set[str]) -> list[str]:
    """Committed media that neither the README nor LEGACY_MEDIA accounts for."""
    return sorted(
        str(path.relative_to(ROOT))
        for path in (ROOT / "assets").rglob("*")
        if path.is_file()
        and path.suffix.lower() in MEDIA_SUFFIXES
        and str(path.relative_to(ROOT)) not in referenced
        and str(path.relative_to(ROOT)) not in LEGACY_MEDIA
    )


def check_readme_refs(report: Report) -> None:
    if not report.check("readme.present", README.is_file(), str(README.relative_to(ROOT))):
        return
    text = README.read_text(encoding="utf-8")
    refs = readme_asset_refs(text)
    report.check("readme.asset_refs", bool(refs), f"{len(refs)} local asset reference(s)")

    missing = [r for r in refs if not (ROOT / r).exists()]
    report.check(
        "readme.asset_paths",
        not missing,
        "every referenced asset exists" if not missing else f"missing: {', '.join(missing)}",
    )

    orphans = find_orphans(set(refs))
    if orphans:
        report.warn(f"media committed but not referenced by README.md: {', '.join(orphans)}")

    # The profile must keep its own navigation: the official site in the hero
    # and footer, and a link to each public repository.
    site = text.count("https://www.yaslogist.com")
    repos = text.count("https://github.com/YASLOGIST")
    report.check(
        "readme.site_links",
        site >= 2 and repos >= 10,
        f"{site} official-site link(s), {repos} repository link(s)",
    )
    report.check("readme.no_tabs", "\t" not in text, "no tab characters")
    # An unbalanced fence silently swallows the rest of the page on GitHub.
    report.check(
        "readme.fences",
        text.count("\n```") % 2 == 0,
        f"{text.count(chr(10) + '```')} code fences (balanced)",
    )
    report.check(
        "readme.hero_block",
        text.lstrip().startswith("<div align=\"center\">"),
        "README opens with a centred hero block",
    )


# --------------------------------------------------------------------------
# GIF structure (standard library)
# --------------------------------------------------------------------------
@dataclass
class GifFacts:
    signature: bytes = b""
    canvas: tuple[int, int] = (0, 0)
    frames: int = 0
    delays_ms: list[int] = field(default_factory=list)
    loop: int | None = None
    has_app_ext: bool = False
    comment: bytes = b""
    trailer: bool = False
    trailing_bytes: int = 0
    local_tables: list[bytes] = field(default_factory=list)
    global_table: bytes = b""
    bounds: list[tuple[int, int, int, int]] = field(default_factory=list)

    @property
    def uniform_delay(self) -> int | None:
        return self.delays_ms[0] if self.delays_ms and len(set(self.delays_ms)) == 1 else None

    @property
    def single_palette(self) -> bool:
        return bool(self.global_table) and all(t == self.global_table for t in self.local_tables)


def parse_gif(path: Path) -> GifFacts:
    """Walk the GIF block structure. Raises ValueError on a malformed file."""
    data = path.read_bytes()
    facts = GifFacts(signature=data[:6])
    if len(data) < 13 or facts.signature not in (b"GIF87a", b"GIF89a"):
        raise ValueError(f"not a GIF: leading bytes {data[:6]!r}")
    width, height, packed, _bg, _aspect = struct.unpack("<HHBBB", data[6:13])
    facts.canvas = (width, height)
    pos = 13
    if packed & 0x80:
        size = 3 * (2 ** ((packed & 0x07) + 1))
        facts.global_table = data[pos:pos + size]
        pos += size
    if len(facts.global_table) != 3 * (2 ** ((packed & 0x07) + 1)):
        raise ValueError("global colour table is truncated")

    def read_subblocks(at: int) -> tuple[bytes, int]:
        out = bytearray()
        while True:
            if at >= len(data):
                raise ValueError("sub-block chain runs past end of file")
            size = data[at]
            at += 1
            if size == 0:
                return bytes(out), at
            out += data[at:at + size]
            at += size

    pending_delay = 0
    while pos < len(data):
        block = data[pos]
        pos += 1
        if block == 0x3B:                                 # trailer
            facts.trailer = True
            facts.trailing_bytes = len(data) - pos
            break
        if block == 0x21:                                 # extension
            label = data[pos]
            pos += 1
            if label == 0xF9:                             # graphic control
                size = data[pos]
                body = data[pos + 1:pos + 1 + size]
                pos += 1 + size
                if len(body) < 3 or data[pos] != 0:
                    raise ValueError("malformed graphic control extension")
                pos += 1
                pending_delay = struct.unpack("<H", body[1:3])[0] * 10
            elif label == 0xFF:                           # application
                size = data[pos]
                ident = data[pos + 1:pos + 1 + size]
                pos += 1 + size
                payload, pos = read_subblocks(pos)
                facts.has_app_ext = True
                if ident.startswith(b"NETSCAPE") and len(payload) >= 3:
                    facts.loop = struct.unpack("<H", payload[1:3])[0]
            elif label == 0xFE:                           # comment
                facts.comment, pos = read_subblocks(pos)
            else:
                _, pos = read_subblocks(pos)
        elif block == 0x2C:                               # image descriptor
            if pos + 9 > len(data):
                raise ValueError("image descriptor runs past end of file")
            left, top, fw, fh = struct.unpack("<4H", data[pos:pos + 8])
            packed_img = data[pos + 8]
            pos += 9
            if packed_img & 0x80:
                size = 3 * (2 ** ((packed_img & 0x07) + 1))
                facts.local_tables.append(data[pos:pos + size])
                pos += size
            pos += 1                                      # LZW minimum code size
            _, pos = read_subblocks(pos)
            facts.frames += 1
            facts.delays_ms.append(pending_delay)
            facts.bounds.append((left, top, fw, fh))
            pending_delay = 0
        else:
            raise ValueError(f"unexpected block 0x{block:02x} at offset {pos - 1}")
    if not facts.trailer:
        raise ValueError("missing GIF trailer (file is truncated)")
    return facts


def renderer_pin() -> str | None:
    """The Pillow version the committed artwork was generated with."""
    text = BUILD_HERO.read_text(encoding="utf-8")
    match = re.search(r'^RENDERER_PIN\s*=\s*["\']([^"\']+)["\']', text, re.MULTILINE)
    return match.group(1) if match else None


def scene_constants() -> dict[str, tuple[int, int]]:
    """Read the generator's canvas/timing constants without importing scene.

    Importing the scene module would drag in Pillow and NumPy; the constants are
    what the committed GIF must agree with, so a textual read is enough.
    """
    text = SCENE.read_text(encoding="utf-8")
    found: dict[str, tuple[int, int]] = {}
    for name, pattern in (
        ("W,H", r"^W,\s*H\s*=\s*(\d+),\s*(\d+)\b"),
        ("FRAMES,DELAY", r"^FRAMES\s*=\s*(\d+).*?^DELAY_MS\s*=\s*(\d+)\b"),
    ):
        match = re.search(pattern, text, re.MULTILINE | re.DOTALL)
        if match:
            found[name] = (int(match.group(1)), int(match.group(2)))
    return found


def check_gif_structure(report: Report) -> GifFacts | None:
    try:
        facts = parse_gif(HERO)
    except (OSError, ValueError) as exc:
        report.fail("hero.structure", f"{HERO.name}: {exc}")
        return None

    w, h = facts.canvas
    report.ok("hero.structure",
              f"{facts.signature.decode('ascii', 'replace')}, {w}x{h}, "
              f"{facts.frames} frames, trailer intact")

    report.check("hero.frames", facts.frames > 1, f"{facts.frames} frames")
    report.check(
        "hero.timing",
        facts.uniform_delay is not None,
        f"uniform {facts.uniform_delay} ms/frame → "
        f"{facts.frames * (facts.uniform_delay or 0) / 1000:.2f} s loop",
    )
    report.check("hero.loop", facts.has_app_ext and facts.loop == 0,
                 f"NETSCAPE2.0 loop count {facts.loop} (0 = infinite)")
    report.check("hero.trailer", facts.trailer and facts.trailing_bytes == 0,
                 "clean EOF" if facts.trailing_bytes == 0
                 else f"{facts.trailing_bytes} trailing byte(s)")
    report.check("hero.palette", facts.single_palette,
                 f"one {len(facts.global_table) // 3}-colour table shared by all frames")
    inside = all(l + fw <= w and t + fh <= h for l, t, fw, fh in facts.bounds)
    report.check("hero.bounds", inside, "every frame rect fits the canvas")
    report.check("hero.comment", b"schematic" in facts.comment.lower(),
                 "provenance comment present")

    constants = scene_constants()
    canvas = constants.get("W,H")
    report.check(
        "scene.canvas",
        canvas == (w, h),
        f"scene.py {canvas} vs hero {w}x{h}",
    )
    timing = constants.get("FRAMES,DELAY")
    report.check(
        "scene.timing",
        timing == (facts.frames, facts.uniform_delay),
        f"scene.py FRAMES={timing[0] if timing else '?'}, "
        f"DELAY_MS={timing[1] if timing else '?'} vs hero {facts.frames}x"
        f"{facts.uniform_delay} ms",
    )
    return facts


def check_still(path: Path, name: str, report: Report, expected: tuple[int, int] | None = None) -> None:
    """Validate a committed still (PNG header, or reuse the GIF walk)."""
    if not path.is_file():
        report.fail(name, f"missing {path.relative_to(ROOT)}")
        return
    data = path.read_bytes()[:32]
    if path.suffix.lower() == ".png":
        if not data.startswith(b"\x89PNG\r\n\x1a\n"):
            report.fail(name, "missing PNG signature")
            return
        width, height, depth, colour = struct.unpack(">IIBB", data[16:26])
        size_ok = expected is None or (width, height) == expected
        report.check(
            name,
            size_ok and depth == 8 and colour in (2, 6),
            f"{width}x{height}, {depth}-bit, colour type {colour}"
            + ("" if size_ok else f" (expected {expected[0]}x{expected[1]})"),
        )
    else:
        try:
            facts = parse_gif(path)
        except ValueError as exc:
            report.fail(name, str(exc))
            return
        report.check(
            name,
            facts.trailer and facts.frames > 1 and facts.loop == 0,
            f"{facts.canvas[0]}x{facts.canvas[1]}, {facts.frames} frames, "
            f"loop {facts.loop}, clean EOF",
        )


def check_mark(report: Report) -> None:
    sys.path.insert(0, str(README_DIR))
    try:
        from mark import MarkParseError, glyph_area_fraction, load_mark
    except ImportError as exc:  # pragma: no cover
        report.fail("mark.parse", f"cannot import assets/readme/mark.py: {exc}")
        return
    try:
        geometry = load_mark(MARK_SVG)
    except MarkParseError as exc:
        report.fail("mark.parse", str(exc))
        return
    report.check(
        "mark.parse",
        len(geometry.polygons) == 2 and geometry.ring_radius > 0,
        f"viewBox {geometry.view_box[2]:.0f}x{geometry.view_box[3]:.0f}, "
        f"ring r={geometry.ring_radius:g}, stroke {geometry.ring_stroke:g}, "
        f"{len(geometry.polygons)} glyph paths, "
        f"ink {glyph_area_fraction(geometry) * 100:.1f}% of the ring box",
    )


# --------------------------------------------------------------------------
# Pixel checks (Pillow)
# --------------------------------------------------------------------------
def check_pixels(report: Report, strict: bool) -> None:
    try:
        from PIL import Image, ImageSequence
    except ImportError:
        report.skip("hero.pixels", "Pillow is not installed")
        if strict:
            report.fail("hero.pixels.required", "Pillow is required by --strict")
        return

    with Image.open(HERO) as hero:
        frames = [
            (frame.copy(), frame.convert("L"))
            for frame in ImageSequence.Iterator(hero)
        ]
        durations = {frame.info.get("duration") for frame, _ in frames}

    lums = [grey for _, grey in frames]
    report.check(
        "hero.pixels.decode",
        len(lums) >= 2 and lums[0].size == (lums[0].width, lums[0].height),
        f"{len(lums)} frames decoded at "
        f"{lums[0].width}x{lums[0].height}",
    )
    report.check(
        "hero.pixels.durations",
        len(durations) == 1,
        f"decoded frame durations {sorted(d for d in durations if d is not None)} ms",
    )

    from PIL import ImageChops, ImageStat

    stds = [ImageStat.Stat(grey).stddev[0] for grey in lums]
    report.check(
        "hero.pixels.not_blank",
        min(stds) >= MIN_FRAME_STD,
        f"per-frame luminance std {min(stds):.1f}–{max(stds):.1f} "
        f"(blank frame would be < {MIN_FRAME_STD:g})",
    )

    steps: list[float] = []
    shares: list[float] = []
    mean_deltas: list[float] = []
    for index in range(len(lums)):
        nxt = lums[(index + 1) % len(lums)]
        diff = ImageChops.difference(lums[index], nxt)
        steps.append(ImageStat.Stat(diff).mean[0])
        histogram = diff.histogram()
        changed = sum(histogram[3:])
        shares.append(100.0 * changed / (lums[index].width * lums[index].height))
        mean_deltas.append(
            abs(ImageStat.Stat(lums[index]).mean[0] - ImageStat.Stat(nxt).mean[0])
        )
    seam_step = steps[-1]
    mid = sorted(steps[:-1])
    median_step = mid[len(mid) // 2]
    p95_step = mid[int(len(mid) * 0.95)]

    # Loop continuity: the wrap-around step must not be larger than a typical
    # mid-loop step, otherwise the loop visibly cuts.
    seam_share, mid_share = shares[-1], sorted(shares[:-1])[len(shares[:-1]) // 2]
    report.check(
        "hero.pixels.loop_seam",
        seam_step <= median_step * 1.5 and seam_share <= mid_share,
        f"seam {seam_share:.2f}% of pixels changed vs {mid_share:.2f}% typical",
    )

    # No flicker: global brightness may never jump by more than 1/255 between
    # consecutive frames. Per-pixel motion is expected (routes, camera drift)
    # so that distribution is reported rather than asserted tightly.
    report.check(
        "hero.pixels.smooth",
        max(mean_deltas) <= MAX_MEAN_STEP,
        f"brightness step max {max(mean_deltas):.2f}/255 "
        f"(limit {MAX_MEAN_STEP:g}); per-pixel step median {median_step:.2f}, "
        f"p95 {p95_step:.2f}",
    )
    report.check(
        "hero.pixels.step_budget",
        median_step <= MAX_MEDIAN_STEP and p95_step <= MAX_P95_STEP,
        f"median {median_step:.2f} ≤ {MAX_MEDIAN_STEP:g}, "
        f"p95 {p95_step:.2f} ≤ {MAX_P95_STEP:g} (regression guard on motion budget)",
    )


def check_reproduces_commit(report: Report, index: int = 100) -> None:
    """Re-render one frame from `scene.py` and compare it with the committed GIF.

    This is what catches a *stale* artwork file: the generator constants can
    agree with the GIF while the scene code has moved on. Only one frame is
    re-rendered (a few seconds), and the render is mapped through the GIF's own
    palette first, so encoder quantisation is not counted as a difference.

    Byte-exactness is only expected under the pinned Pillow build, because
    FreeType rasterises the bundled faces differently across versions. On any
    other version the same comparison runs with a coarser, structural tolerance
    and says so, rather than either failing on a dependency bump or silently
    skipping the check.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        report.skip("hero.reproduces", "Pillow and NumPy are required")
        return
    sys.path.insert(0, str(README_DIR))
    try:
        import scene
    except Exception as exc:  # pragma: no cover - dependency problems
        report.skip("hero.reproduces", f"cannot import scene.py: {exc}")
        return

    constants = scene_constants()
    frames = constants.get("FRAMES,DELAY", (0, 0))[0]
    if not frames or not 0 <= index < frames:
        report.fail("hero.reproduces", f"frame {index} is outside the loop")
        return

    rendered = scene.Scene().frame(index / frames)
    with Image.open(HERO) as hero:
        hero.seek(0)
        palette = Image.new("P", (1, 1))
        palette.putpalette(hero.getpalette())
        hero.seek(index)
        committed = np.asarray(hero.convert("RGB"), dtype=np.int16)

    mapped = rendered.quantize(palette=palette, dither=Image.Dither.NONE).convert("RGB")
    delta = np.abs(np.asarray(mapped, dtype=np.int16) - committed)
    mean = float(delta.mean())
    outliers = float((delta.max(axis=2) > 8).mean())

    pin = renderer_pin()
    installed = Image.__version__
    pinned = pin is not None and installed == pin
    if pinned:
        ok = mean <= MAX_REPRODUCE_DIFF and outliers <= MAX_REPRODUCE_OUTLIERS
        budget = f"limits {MAX_REPRODUCE_DIFF:g}/255 mean, {MAX_REPRODUCE_OUTLIERS * 100:g}% outliers"
    else:
        # Downsample by 4 before looking at the tail: renderer differences are
        # thin type edges, whereas moved geometry survives averaging.
        h, w = delta.shape[0] // 4 * 4, delta.shape[1] // 4 * 4
        coarse = delta[:h, :w].reshape(h // 4, 4, w // 4, 4, 3).mean(axis=(1, 3))
        p99 = float(np.percentile(coarse, 99))
        mean = max(mean, 0.0)
        ok = mean <= MAX_LOOSE_DIFF and p99 <= MAX_LOOSE_P99
        budget = (f"structural limits {MAX_LOOSE_DIFF:g}/255 mean, "
                  f"p99 {MAX_LOOSE_P99:g} (coarse)")
        report.warn(
            f"hero.reproduces ran on Pillow {installed}, but the artwork was "
            f"generated with {pin or 'an unknown version'}: compared structurally "
            f"instead of byte-for-byte"
        )
    report.check(
        "hero.reproduces",
        ok,
        f"frame {index} re-rendered from scene.py vs committed GIF: mean "
        f"Δ {mean:.2f}/255, {outliers * 100:.2f}% of pixels off by >8/255 "
        f"({budget}; Pillow {installed}, pinned {pin or 'n/a'})",
    )


def check_renderer_pin(report: Report) -> None:
    """CI must install the renderer the artwork was generated with.

    If the two drift apart the reproduction check silently degrades to its
    structural fallback, which would quietly weaken the guarantee the README
    makes. Cheaper to fail here than to notice months later.
    """
    pin = renderer_pin()
    if pin is None:
        report.fail("workflow.renderer_pin", "build_hero.py has no RENDERER_PIN")
        return
    if not WORKFLOW.is_file():
        report.skip("workflow.renderer_pin", "no CI workflow in this checkout")
        return
    text = WORKFLOW.read_text(encoding="utf-8")
    pins = set(re.findall(r'Pillow==([0-9][0-9A-Za-z.\-]*)', text))
    report.check(
        "workflow.renderer_pin",
        pins == {pin},
        f"workflow installs Pillow {', '.join(sorted(pins)) or 'unpinned'}; "
        f"artwork pinned to {pin}",
    )


def check_stills(report: Report) -> None:
    constants = scene_constants()
    expected = constants.get("W,H")
    check_still(POSTER, "poster.png", report, expected)
    check_still(SIGNAL, "signal.gif", report)
    check_still(SIGNATURE, "signature.png", report)


# --------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--quiet", action="store_true", help="only failures and warnings")
    parser.add_argument("--strict", action="store_true",
                        help="treat missing optional dependencies as failures")
    parser.add_argument("--reproduce", nargs="?", type=int, const=100, default=None,
                        metavar="FRAME",
                        help="re-render one frame from scene.py and compare it with the "
                             "committed GIF (slow: needs Pillow and NumPy)")
    args = parser.parse_args(argv)

    report = Report()
    check_readme_refs(report)
    check_gif_structure(report)
    check_stills(report)
    check_mark(report)
    check_renderer_pin(report)
    check_pixels(report, args.strict)
    if args.reproduce is not None:
        check_reproduces_commit(report, args.reproduce)

    print("YASLOGIST profile asset verification")
    print(report.render(quiet=args.quiet))
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

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
import hashlib
import json
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
STAMP = README_DIR / "yaslogist-hero.build.json"

# Regression thresholds derived from the committed artwork. They are not
# aspirational targets: each one is a little looser than the measured value so
# ordinary deterministic noise cannot trip it, while a real regression can.
MIN_FRAME_STD = 5.0          # a blank frame would fall near 0 (measured ~33.5)
MAX_MEAN_STEP = 1.0          # /255 global brightness change per frame (measured 0.54)
MAX_MEDIAN_STEP = 0.8        # /255 per pixel (measured 0.43)
MAX_P95_STEP = 3.5           # /255 per pixel (measured 2.64)
# Re-rendering the artwork is *not* bit-reproducible across machines (FreeType
# inside the Pillow wheel, NumPy SIMD paths, palette mapping on near-threshold
# pixels): frame 100 differs by 0.57/255 between Pillow 11.3 and 13.0, and by
# 0.72/255 between local Pillow 13.0 and a GitHub runner with the same version.
# So freshness is verified from a build stamp instead of from pixels. See
# `check_stamp` and `--probe`.
MAX_PROBE_DIFF = 3.0   # mean channel error before --probe warns (measured 0.6-0.7)

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
        if len(facts.global_table) != size:
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
            if at + size > len(data):
                raise ValueError("sub-block data is truncated")
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
            if pos >= len(data):
                raise ValueError("extension label is truncated")
            label = data[pos]
            pos += 1
            if label == 0xF9:                             # graphic control
                if pos >= len(data):
                    raise ValueError("graphic control extension is truncated")
                size = data[pos]
                body = data[pos + 1:pos + 1 + size]
                pos += 1 + size
                if size != 4 or len(body) != 4 or pos >= len(data) or data[pos] != 0:
                    raise ValueError("malformed graphic control extension")
                pos += 1
                pending_delay = struct.unpack("<H", body[1:3])[0] * 10
            elif label == 0xFF:                           # application
                if pos >= len(data):
                    raise ValueError("application extension is truncated")
                size = data[pos]
                ident = data[pos + 1:pos + 1 + size]
                pos += 1 + size
                if len(ident) != size:
                    raise ValueError("application identifier is truncated")
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
                table = data[pos:pos + size]
                if len(table) != size:
                    raise ValueError("local colour table is truncated")
                facts.local_tables.append(table)
                pos += size
            if pos >= len(data):
                raise ValueError("LZW code size is missing")
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


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def check_stamp(report: Report, facts: GifFacts | None) -> None:
    """The committed artwork must belong to the current generator sources.

    This is the check that catches stale artwork: edit `scene.py` (or the mark
    SVG, or a font) without rebuilding the GIF and the stamp no longer matches.
    It is exact and environment-independent, unlike comparing rendered pixels.
    """
    if not STAMP.is_file():
        report.fail("artwork.stamp", f"missing {STAMP.relative_to(ROOT)} — run "
                                     f"assets/readme/build_hero.py")
        return
    try:
        stamp = json.loads(STAMP.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        report.fail("artwork.stamp", f"unreadable stamp: {exc}")
        return

    inputs = stamp.get("inputs")
    if not isinstance(inputs, dict) or not inputs:
        report.fail("artwork.stamp", "stamp records no input hashes")
        return

    required_inputs = {
        "assets/readme/build_hero.py", "assets/readme/mark.py",
        "assets/readme/scene.py", "assets/readme/yaslogist-mark.svg",
        *(f"assets/readme/fonts/{name}.ttf" for name in (
            "Inter-ExtraBold", "Inter-Regular", "Inter-SemiBold",
            "JetBrainsMono-Regular", "JetBrainsMono-SemiBold")),
    }
    missing_entries = sorted(required_inputs - inputs.keys())
    if missing_entries:
        report.fail("artwork.stamp_inputs", "missing input entries: " + ", ".join(missing_entries))
    fingerprint = hashlib.sha256(
        "\n".join(f"{name}:{digest}" for name, digest in sorted(inputs.items())).encode()
    ).hexdigest()
    report.check("artwork.fingerprint", stamp.get("fingerprint") == fingerprint,
                 "input fingerprint matches" if stamp.get("fingerprint") == fingerprint
                 else "input fingerprint does not match stamp entries")

    stale = []
    missing = []
    for name, digest in sorted(inputs.items()):
        path = ROOT / name
        if not path.is_file():
            missing.append(name)
        elif _sha256(path) != digest:
            stale.append(name)
    report.check(
        "artwork.stamp",
        not stale and not missing,
        "artwork was built from the current sources"
        if not stale and not missing
        else f"stale inputs: {', '.join(stale + missing)} — rebuild with "
             f"assets/readme/build_hero.py",
    )

    # The stamp describes the artwork that exists now, not one that has been
    # replaced or hand-edited since.
    artwork = stamp.get("artwork")
    if not isinstance(artwork, dict):
        artwork = {}
    problems = [f"{name} missing from stamp" for name in (HERO.name, POSTER.name)
                if name not in artwork]
    for name, recorded in sorted(artwork.items()):
        if not isinstance(recorded, dict):
            problems.append(f"{name} has invalid metadata")
            continue
        path = README_DIR / name
        if not path.is_file():
            problems.append(f"{name} missing")
            continue
        if path.stat().st_size != recorded.get("bytes"):
            problems.append(f"{name} size {path.stat().st_size} != {recorded.get('bytes')}")
        elif _sha256(path) != recorded.get("sha256"):
            problems.append(f"{name} hash changed")
    report.check(
        "artwork.stamp_files",
        not problems,
        "committed artwork matches its build stamp"
        if not problems
        else "; ".join(problems) + " — rebuild rather than hand-editing artwork",
    )

    renderer = stamp.get("renderer") or {}
    report.ok(
        "artwork.provenance",
        f"built with Pillow {renderer.get('pillow', '?')} / NumPy "
        f"{renderer.get('numpy', '?')}; {len(inputs)} hashed input(s)",
    )
    if facts is not None:
        canvas = tuple(stamp.get("canvas") or ())
        report.check(
            "artwork.stamp_timing",
            canvas == facts.canvas
            and stamp.get("frames") == facts.frames
            and stamp.get("delay_ms") == facts.uniform_delay,
            f"stamp says {canvas}, {stamp.get('frames')} frames @ "
            f"{stamp.get('delay_ms')} ms; GIF is {facts.canvas}, {facts.frames} @ "
            f"{facts.uniform_delay} ms",
        )


def check_scene_determinism(report: Report, index: int = 0) -> None:
    """The scene must render the same pixels twice in the same process.

    The artwork's loop, palette and motion all assume a deterministic scene; an
    unseeded random call or set iteration would break that silently.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        report.skip("scene.deterministic", "Pillow and NumPy are required")
        return
    sys.path.insert(0, str(README_DIR))
    try:
        import scene
    except Exception as exc:  # pragma: no cover
        report.fail("scene.deterministic", f"cannot import scene.py: {exc}")
        return

    frames = scene_constants().get("FRAMES,DELAY", (0, 0))[0]
    if not frames:
        report.fail("scene.deterministic", "scene.py has no usable FRAMES")
        return
    p = (index % frames) / frames
    first = np.asarray(scene.Scene().frame(p))
    second = np.asarray(scene.Scene().frame(p))
    same = np.array_equal(first, second)
    report.check(
        "scene.deterministic",
        same,
        f"frame {index} rendered twice on Pillow {Image.__version__}: "
        + ("identical" if same else f"{int((first != second).sum())} differing bytes"),
    )


def probe_render(report: Report, index: int) -> None:
    """Report how far a fresh render is from the committed frame (informational).

    Never a pass/fail gate: the difference is dominated by the renderer build,
    so a threshold here would fail on dependency changes rather than on real
    regressions. It is still useful right after a rebuild.
    """
    try:
        import numpy as np
        from PIL import Image
    except ImportError:
        report.skip("probe.render", "Pillow and NumPy are required")
        return
    sys.path.insert(0, str(README_DIR))
    try:
        import scene
    except Exception as exc:  # pragma: no cover
        report.skip("probe.render", f"cannot import scene.py: {exc}")
        return

    frames = scene_constants().get("FRAMES,DELAY", (0, 0))[0]
    if not frames or not 0 <= index < frames:
        report.fail("probe.render", f"frame {index} is outside the loop")
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
    detail = (f"frame {index}: mean Δ {mean:.2f}/255, "
              f"{(delta.max(axis=2) > 8).mean() * 100:.2f}% of pixels off by >8/255 "
              f"(Pillow {Image.__version__})")
    if mean > MAX_PROBE_DIFF:
        report.warn(f"probe.render {detail} — larger than renderer noise usually explains")
    else:
        report.ok("probe.render", detail)


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
    parser.add_argument("--probe", nargs="?", type=int, const=100, default=None,
                        metavar="FRAME",
                        help="re-render one frame and report how far it is from the "
                             "committed GIF (informational, never a pass/fail gate)")
    args = parser.parse_args(argv)

    report = Report()
    check_readme_refs(report)
    facts = check_gif_structure(report)
    check_stills(report)
    check_mark(report)
    check_stamp(report, facts)
    check_scene_determinism(report)
    check_pixels(report, args.strict)
    if args.probe is not None:
        probe_render(report, args.probe)

    if args.strict:
        for name, _, detail in list(report.skips):
            report.fail(name + ".required", detail)

    print("YASLOGIST profile asset verification")
    print(report.render(quiet=args.quiet))
    return 1 if report.failures else 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Read the official YASLOGIST YL mark straight from its SVG master.

`yaslogist-mark.svg` is the vector master for the brand mark. The hero scene
draws the mark from *these* coordinates, so the artwork can never drift from
the master file: editing the SVG is the only way to change the glyphs.

Deliberately dependency-free (standard library only) so it can be unit-tested
without Pillow, NumPy or a GPU, and cheap enough to call at scene build time.

Only the subset actually used by the mark is supported - absolute moves,
absolute lines and close path. Anything else raises `MarkParseError` instead
of guessing, which keeps a malformed edit from silently producing a different
logo.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

SVG_NS = "{http://www.w3.org/2000/svg}"
HERE = Path(__file__).resolve().parent
DEFAULT_MARK = HERE / "yaslogist-mark.svg"

# Path tokeniser: one command letter or one number.
_TOKEN = re.compile(r"([MmLlHhVvZzCcSsQqTtAa])|(-?\d*\.?\d+(?:[eE][-+]?\d+)?)")

SUPPORTED_COMMANDS = ("M", "L", "Z")


class MarkParseError(ValueError):
    """The SVG does not look like the mark this renderer can draw."""


@dataclass(frozen=True)
class MarkGeometry:
    """Measured geometry of the circular YL mark, in SVG user units."""

    view_box: tuple[float, float, float, float]
    center: tuple[float, float]
    ring_radius: float
    ring_stroke: float
    polygons: tuple[tuple[tuple[float, float], ...], ...]

    def scaled(self, radius: float) -> "ScaledMark":
        """Map the mark onto a drawn ring of `radius` pixels."""
        if radius <= 0:
            raise ValueError("radius must be positive")
        return ScaledMark(self, radius / self.ring_radius)


@dataclass(frozen=True)
class ScaledMark:
    """The mark mapped to a drawn ring radius, still centred on the SVG centre."""

    geometry: MarkGeometry
    scale: float

    def point(self, x: float, y: float) -> tuple[float, float]:
        cx, cy = self.geometry.center
        return ((x - cx) * self.scale, (y - cy) * self.scale)

    def polygon(self, index: int) -> tuple[tuple[float, float], ...]:
        return tuple(self.point(x, y) for x, y in self.geometry.polygons[index])

    @property
    def stroke_width(self) -> float:
        return self.geometry.ring_stroke * self.scale


def parse_path(d: str) -> tuple[tuple[tuple[float, float], ...], ...]:
    """Parse an absolute M/L/Z path into closed polygons."""
    tokens = [tok for pair in _TOKEN.findall(d) for tok in pair if tok]
    polygons: list[list[tuple[float, float]]] = []
    current: list[tuple[float, float]] = []
    cmd: str | None = None
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok in "MmLlHhVvZzCcSsQqTtAa":
            if tok not in SUPPORTED_COMMANDS:
                raise MarkParseError(
                    f"unsupported path command {tok!r}: the mark may only use "
                    f"{', '.join(SUPPORTED_COMMANDS)}"
                )
            cmd = tok
            i += 1
            if cmd == "Z":
                if len(current) >= 3:
                    polygons.append(current)
                current = []
                cmd = None
            continue
        if cmd is None:
            raise MarkParseError(f"coordinates without a command in path {d!r}")
        if i + 1 >= len(tokens) or tokens[i + 1] in "MmLlHhVvZzCcSsQqTtAa":
            raise MarkParseError(f"incomplete coordinate pair after {cmd!r} in {d!r}")
        x, y = float(tokens[i]), float(tokens[i + 1])
        if cmd == "M":
            if len(current) >= 3:
                polygons.append(current)
            current = [(x, y)]
            cmd = "L"  # subsequent pairs are implicit lineto, per the SVG spec
        else:
            current.append((x, y))
        i += 2
    if len(current) >= 3:
        polygons.append(current)
    if not polygons:
        raise MarkParseError("path contains no closed polygon")
    return tuple(tuple(p) for p in polygons)


def parse_svg_mark(source: str | Path = DEFAULT_MARK) -> MarkGeometry:
    """Parse the committed SVG mark into drawable geometry."""
    path = Path(source)
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:  # pragma: no cover - surfaced by the verifier too
        raise MarkParseError(f"cannot read mark SVG {path}: {exc}") from exc
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise MarkParseError(f"{path.name} is not well-formed XML: {exc}") from exc

    view_box_raw = root.get("viewBox", "")
    try:
        view_box = tuple(float(v) for v in re.split(r"[,\s]+", view_box_raw.strip()) if v)
    except ValueError as exc:
        raise MarkParseError(f"{path.name} has an unparsable viewBox {view_box_raw!r}") from exc
    if len(view_box) != 4 or view_box[2] <= 0 or view_box[3] <= 0:
        raise MarkParseError(f"{path.name} needs a 4-number viewBox, got {view_box_raw!r}")

    ring = root.find(f"{SVG_NS}circle")
    if ring is None:
        raise MarkParseError(f"{path.name} has no <circle> ring")
    radius = float(ring.get("r", "0"))
    if radius <= 0:
        raise MarkParseError(f"{path.name} ring has no usable radius")
    cx = float(ring.get("cx", view_box[0] + view_box[2] / 2))
    cy = float(ring.get("cy", view_box[1] + view_box[3] / 2))
    stroke_attr = (ring.get("stroke-width") or "").strip()
    if not stroke_attr:
        raise MarkParseError(f"{path.name} ring has no stroke-width")
    stroke = float(stroke_attr)

    polygons: list[tuple[tuple[float, float], ...]] = []
    for element in root.findall(f"{SVG_NS}path"):
        polygons.extend(parse_path(element.get("d", "")))
    if not polygons:
        raise MarkParseError(f"{path.name} has no glyph <path> elements")

    return MarkGeometry(
        view_box=view_box,  # type: ignore[arg-type]
        center=(cx, cy),
        ring_radius=radius,
        ring_stroke=stroke,
        polygons=tuple(polygons),
    )


def polygon_area(points: tuple[tuple[float, float], ...]) -> float:
    """Shoelace area of a simple polygon, in square user units."""
    total = 0.0
    for (x1, y1), (x2, y2) in zip(points, points[1:] + points[:1]):
        total += x1 * y2 - x2 * y1
    return abs(total) * 0.5


_MARK_CACHE: dict[Path, MarkGeometry] = {}


def load_mark(source: str | Path = DEFAULT_MARK) -> MarkGeometry:
    """Parse once, then reuse - the scene calls this for every rebuild."""
    key = Path(source).resolve()
    cached = _MARK_CACHE.get(key)
    if cached is None:
        cached = parse_svg_mark(key)
        _MARK_CACHE[key] = cached
    return cached


def glyph_area_fraction(geometry: MarkGeometry) -> float:
    """Glyph ink as a fraction of the ring's enclosing square.

    Used by the tests and the verifier as a cheap, geometry-derived invariant
    of the rendered mark.
    """
    ink = sum(polygon_area(p) for p in geometry.polygons)
    side = 2.0 * geometry.ring_radius
    return ink / (side * side)


__all__ = [
    "DEFAULT_MARK",
    "MarkGeometry",
    "MarkParseError",
    "ScaledMark",
    "glyph_area_fraction",
    "load_mark",
    "parse_path",
    "parse_svg_mark",
    "polygon_area",
]

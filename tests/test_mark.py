#!/usr/bin/env python3
"""Tests for the YASLOGIST mark parser (standard library only).

`mark.py` is the single source of truth for the brand-mark geometry, so these
tests guard the contract the hero scene depends on: a 512-unit viewBox, a
238-unit ring, two glyph outlines, and a parser that refuses anything it cannot
draw exactly rather than silently approximating it.
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

README_DIR = Path(__file__).resolve().parent.parent / "assets" / "readme"
sys.path.insert(0, str(README_DIR))

import mark  # noqa: E402


class ParseSvgMarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.geometry = mark.load_mark()

    def test_view_box_and_ring(self) -> None:
        self.assertEqual(self.geometry.view_box, (0.0, 0.0, 512.0, 512.0))
        self.assertEqual(self.geometry.center, (256.0, 256.0))
        self.assertEqual(self.geometry.ring_radius, 238.0)
        self.assertEqual(self.geometry.ring_stroke, 16.0)

    def test_two_glyph_outlines(self) -> None:
        self.assertEqual(len(self.geometry.polygons), 2, "the mark is a Y and an L")
        self.assertEqual([len(p) for p in self.geometry.polygons], [9, 7])

    def test_glyphs_fit_inside_the_ring(self) -> None:
        cx, cy = self.geometry.center
        limit = self.geometry.ring_radius
        for polygon in self.geometry.polygons:
            for x, y in polygon:
                self.assertLess(abs(x - cx), limit, f"{x} outside the ring")
                self.assertLess(abs(y - cy), limit, f"{y} outside the ring")

    def test_ink_coverage_is_stable(self) -> None:
        # Measured from the committed master; a redrawn logo would move this.
        fraction = mark.glyph_area_fraction(self.geometry)
        self.assertGreater(fraction, 0.13)
        self.assertLess(fraction, 0.19)

    def test_polygons_are_not_self_degenerate(self) -> None:
        for polygon in self.geometry.polygons:
            self.assertGreater(mark.polygon_area(polygon), 1000.0)

    def test_loader_is_cached(self) -> None:
        self.assertIs(mark.load_mark(), mark.load_mark())

    def test_missing_file_reports_clearly(self) -> None:
        with self.assertRaises(mark.MarkParseError):
            mark.parse_svg_mark(README_DIR / "does-not-exist.svg")


class ScaleTest(unittest.TestCase):
    def test_points_are_centred_on_the_mark(self) -> None:
        scaled = mark.load_mark().scaled(112.0)
        points = scaled.polygon(0)
        # The SVG centre maps to the local origin, so glyph points straddle it.
        xs = [x for x, _ in points]
        self.assertLess(min(xs), 0.0)
        self.assertGreater(max(xs), 0.0)

    def test_scale_is_radius_over_ring_radius(self) -> None:
        scaled = mark.load_mark().scaled(119.0)
        self.assertAlmostEqual(scaled.scale, 0.5)
        self.assertAlmostEqual(scaled.stroke_width, 8.0)

    def test_rejects_non_positive_radius(self) -> None:
        for bad in (0, -1, -112.5):
            with self.assertRaises(ValueError):
                mark.load_mark().scaled(bad)


class ParsePathTest(unittest.TestCase):
    def test_closes_and_returns_polygons(self) -> None:
        polygons = mark.parse_path("M 0 0 L 10 0 L 10 10 L 0 10 Z")
        self.assertEqual(len(polygons), 1)
        self.assertEqual(len(polygons[0]), 4)
        self.assertAlmostEqual(mark.polygon_area(polygons[0]), 100.0)

    def test_implicit_lineto_after_move(self) -> None:
        polygons = mark.parse_path("M0 0 L4 0 4 4 0 4 Z")
        self.assertEqual(len(polygons[0]), 4)

    def test_multiple_subpaths(self) -> None:
        polygons = mark.parse_path("M0 0 L2 0 L2 2 Z M5 5 L7 5 L7 7 Z")
        self.assertEqual(len(polygons), 2)

    def test_unsupported_curve_is_refused(self) -> None:
        with self.assertRaises(mark.MarkParseError) as ctx:
            mark.parse_path("M0 0 C 1 1 2 2 3 3 Z")
        self.assertIn("unsupported path command", str(ctx.exception))

    def test_relative_commands_are_refused(self) -> None:
        for d in ("m0 0 l1 1 l1 0 z", "M0 0 L1 1 H4 Z"):
            with self.assertRaises(mark.MarkParseError):
                mark.parse_path(d)

    def test_incomplete_pair_is_refused(self) -> None:
        with self.assertRaises(mark.MarkParseError):
            mark.parse_path("M 0 L 10")

    def test_geometry_without_polygon_is_refused(self) -> None:
        with self.assertRaises(mark.MarkParseError):
            mark.parse_path("M0 0 L1 1")

    def test_bad_svg_is_refused(self) -> None:
        with self.assertRaises(mark.MarkParseError):
            mark.parse_svg_mark(Path(__file__))


if __name__ == "__main__":
    unittest.main()

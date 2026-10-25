#!/usr/bin/env python3
"""Render-level test: the drawn YL mark must match the SVG master's geometry.

The scene used to carry its own copy of the glyph coordinates. It now draws
from `yaslogist-mark.svg` via `mark.py`; this test pins that the rasterised
glyphs still cover the area the vector geometry predicts, so a future edit to
either side cannot silently reshape the brand mark.

Skipped when Pillow/NumPy are unavailable (they are only needed to *generate*
the artwork, never to display it).
"""
from __future__ import annotations

import sys
import unittest
from pathlib import Path

README_DIR = Path(__file__).resolve().parent.parent / "assets" / "readme"
sys.path.insert(0, str(README_DIR))

try:  # pragma: no cover - exercised only when the render deps are installed
    import numpy as np

    import scene
    HAVE_RENDER_DEPS = True
except ImportError:  # pragma: no cover
    HAVE_RENDER_DEPS = False

INK = (244, 248, 248)
RADIUS = 112.0


@unittest.skipUnless(HAVE_RENDER_DEPS, "Pillow and NumPy are not installed")
class RenderedMarkTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        import mark as mark_module

        cls.mark = mark_module
        cls.layer = scene.build_core_mark(RADIUS)
        cls.pixels = np.asarray(cls.layer)

    def test_layer_is_supersampled_full_frame(self) -> None:
        expected = (scene.W + scene.MARGIN * 2) * scene.SS
        self.assertEqual(self.pixels.shape[1], expected)
        self.assertEqual(self.pixels.shape[0], (scene.H + scene.MARGIN * 2) * scene.SS)

    def test_glyph_ink_matches_vector_area(self) -> None:
        """Filled glyph pixels ≈ polygon area × scale² (within 3 %)."""
        geometry = self.mark.load_mark()
        scaled = geometry.scaled(RADIUS)
        ink = (
            (self.pixels[:, :, 3] == 255)
            & (self.pixels[:, :, 0] == INK[0])
            & (self.pixels[:, :, 1] == INK[1])
            & (self.pixels[:, :, 2] == INK[2])
        ).sum()
        expected = sum(self.mark.polygon_area(p) for p in geometry.polygons)
        expected *= (scaled.scale * scene.SS) ** 2
        self.assertGreater(expected, 0)
        self.assertLess(
            abs(ink - expected) / expected, 0.03,
            f"drawn ink {ink:.0f} px vs vector prediction {expected:.0f} px",
        )

    def test_mark_is_rendered_once_per_call_deterministically(self) -> None:
        again = np.asarray(scene.build_core_mark(RADIUS))
        self.assertTrue(np.array_equal(self.pixels, again))

    def test_scene_does_not_keep_its_own_glyph_copy(self) -> None:
        """No second set of logo coordinates may creep back into scene.py."""
        source = (README_DIR / "scene.py").read_text(encoding="utf-8")
        for needle in ("Y_PATH", "L_PATH", "(305, 98)", "(440, 371)"):
            self.assertNotIn(needle, source, f"scene.py still hard-codes {needle}")


if __name__ == "__main__":
    unittest.main()

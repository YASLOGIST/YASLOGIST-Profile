#!/usr/bin/env python3
"""Run the asset verifier over the committed files as part of the test suite.

This is the same check CI runs; having it here means `python3 -m unittest
discover -s tests` alone is enough to know the profile assets are intact.
"""
from __future__ import annotations

import importlib.util
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "tools"))
sys.path.insert(0, str(ROOT / "assets" / "readme"))

import verify_assets  # noqa: E402


class VerifyAssetsTest(unittest.TestCase):
    def test_every_structural_check_passes(self) -> None:
        report = verify_assets.Report()
        verify_assets.check_readme_refs(report)
        verify_assets.check_gif_structure(report)
        verify_assets.check_stills(report)
        verify_assets.check_mark(report)
        failures = [f"{name}: {detail}" for name, _, detail in report.failures]
        self.assertEqual(failures, [], "asset verification failures")

    def test_orphan_warnings_are_reported_not_raised(self) -> None:
        report = verify_assets.Report()
        verify_assets.check_readme_refs(report)
        # Legacy art may stay in the repository; it must never break the build,
        # but it should be visible in the verifier output.
        self.assertFalse(report.failures)

    def test_hero_structural_facts(self) -> None:
        facts = verify_assets.parse_gif(verify_assets.HERO)
        self.assertEqual(facts.signature, b"GIF89a")
        self.assertEqual(facts.canvas, (1920, 720))
        self.assertEqual(facts.frames, 200)
        self.assertEqual(facts.uniform_delay, 50)
        self.assertEqual(facts.loop, 0)
        self.assertTrue(facts.trailer)
        self.assertEqual(facts.trailing_bytes, 0)
        self.assertTrue(facts.single_palette)

    def test_truncated_gif_is_rejected(self) -> None:
        import tempfile

        data = verify_assets.HERO.read_bytes()
        with tempfile.TemporaryDirectory() as tmp:
            broken = Path(tmp) / "broken.gif"
            broken.write_bytes(data[: len(data) // 3])
            with self.assertRaises(ValueError):
                verify_assets.parse_gif(broken)

    def test_orphan_detection_is_actionable(self) -> None:
        # Everything the README references, plus the documented legacy art,
        # must leave no orphans.
        text = verify_assets.README.read_text(encoding="utf-8")
        referenced = set(verify_assets.readme_asset_refs(text))
        self.assertEqual(verify_assets.find_orphans(referenced), [])

        # A committed asset that nobody points at and that is not declared as
        # legacy must still be reported.
        orphans = verify_assets.find_orphans({"assets/does-not-exist.png"})
        self.assertIn("assets/readme/yaslogist-hero.gif", orphans)
        self.assertFalse(set(orphans) & verify_assets.LEGACY_MEDIA)

    def test_legacy_media_still_exists_and_is_unreferenced(self) -> None:
        text = verify_assets.README.read_text(encoding="utf-8")
        referenced = set(verify_assets.readme_asset_refs(text))
        for legacy in verify_assets.LEGACY_MEDIA:
            self.assertTrue((verify_assets.ROOT / legacy).is_file(), legacy)
            self.assertNotIn(legacy, referenced)

    def test_readme_reference_scanner_ignores_remote_urls(self) -> None:
        text = (
            '<img src="./assets/local.png" />'
            '<a href="https://example.com/x.png">site</a>'
            "[link](./assets/other.gif)"
            '<a href="mailto:a@b.c">mail</a>'
        )
        refs = verify_assets.readme_asset_refs(text)
        self.assertEqual(refs, ["assets/local.png", "assets/other.gif"])

    def test_committed_gif_still_matches_its_generator(self) -> None:
        """Re-render one frame and compare it with the committed artwork."""
        missing = [
            module for module in ("PIL", "numpy", "scene")
            if importlib.util.find_spec(module) is None
        ]
        if missing:
            self.skipTest(f"render dependencies not installed: {', '.join(missing)}")

        report = verify_assets.Report()
        verify_assets.check_reproduces_commit(report, index=37)
        self.assertEqual(
            [f"{name}: {detail}" for name, _, detail in report.failures], [],
            "the committed hero no longer reproduces from scene.py",
        )
        self.assertIn("hero.reproduces", [c[0] for c in report.checks])

    def test_scene_constants_are_parsed(self) -> None:
        constants = verify_assets.scene_constants()
        self.assertEqual(constants["W,H"], (1920, 720))
        self.assertEqual(constants["FRAMES,DELAY"], (200, 50))


if __name__ == "__main__":
    unittest.main()

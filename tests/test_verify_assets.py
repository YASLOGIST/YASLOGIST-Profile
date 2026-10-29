#!/usr/bin/env python3
"""Run the asset verifier over the committed files as part of the test suite.

This is the same check CI runs; having it here means `python3 -m unittest
discover -s tests` alone is enough to know the profile assets are intact.
"""
from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

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

    def test_parser_handles_local_palette_and_truncation(self) -> None:
        # A valid one-pixel GIF can use a local palette and no global table.
        data = (b"GIF89a" + b"\x01\x00\x01\x00\x00\x00\x00"
                + b"\x2c\x00\x00\x00\x00\x01\x00\x01\x00\x80"
                + b"\x00\x00\x00\xff\xff\xff"
                + b"\x02\x02\x44\x01\x00\x3b")
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "local.gif"
            path.write_bytes(data)
            facts = verify_assets.parse_gif(path)
            self.assertEqual(facts.frames, 1)
            self.assertFalse(facts.global_table)
            for length in range(len(data)):
                path.write_bytes(data[:length])
                with self.subTest(length=length), self.assertRaises(ValueError):
                    verify_assets.parse_gif(path)

    def test_truncated_extensions_raise_value_error(self) -> None:
        header = b"GIF89a" + b"\x01\x00\x01\x00\x00\x00\x00"
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "broken.gif"
            for suffix in (b"\x21", b"\x21\xf9", b"\x21\xf9\x04\x00",
                           b"\x21\xff", b"\x21\xff\x0bNET"):
                path.write_bytes(header + suffix)
                with self.subTest(suffix=suffix), self.assertRaises(ValueError):
                    verify_assets.parse_gif(path)

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

    def test_build_stamp_matches_the_current_sources(self) -> None:
        """The committed artwork must belong to the current generator sources."""
        report = verify_assets.Report()
        facts = verify_assets.parse_gif(verify_assets.HERO)
        verify_assets.check_stamp(report, facts)
        self.assertEqual([f"{n}: {d}" for n, _, d in report.failures], [])

    def test_stamp_notices_a_changed_source(self) -> None:
        """A source edit without a rebuild must be reported as stale."""
        victim = "assets/readme/scene.py"

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in json.loads(verify_assets.STAMP.read_text())["inputs"]:
                target = root / name
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(verify_assets.ROOT / name, target)
            changed = root / victim
            changed.write_text(changed.read_text(encoding="utf-8") + "\n")
            with mock.patch.object(verify_assets, "ROOT", root):
                report = verify_assets.Report()
                verify_assets.check_stamp(report, None)
            self.assertIn("artwork.stamp", [n for n, _, _ in report.failures])
            self.assertIn(victim, report.failures[0][2])

    def test_stamp_rejects_removed_entries(self) -> None:
        stamp = json.loads(verify_assets.STAMP.read_text(encoding="utf-8"))
        del stamp["inputs"]["assets/readme/scene.py"]
        del stamp["artwork"]["yaslogist-hero.gif"]
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "stamp.json"
            path.write_text(json.dumps(stamp), encoding="utf-8")
            with mock.patch.object(verify_assets, "STAMP", path):
                report = verify_assets.Report()
                verify_assets.check_stamp(report, None)
        failures = {name for name, _, _ in report.failures}
        self.assertTrue({"artwork.stamp_inputs", "artwork.fingerprint",
                         "artwork.stamp_files"} <= failures)

    def test_stamp_records_provenance_and_timing(self) -> None:
        stamp = json.loads(verify_assets.STAMP.read_text(encoding="utf-8"))
        self.assertEqual(stamp["canvas"], [1920, 720])
        self.assertEqual(stamp["frames"], 200)
        self.assertEqual(stamp["delay_ms"], 50)
        self.assertIn("pillow", stamp["renderer"])
        self.assertRegex(stamp["fingerprint"], r"^[0-9a-f]{64}$")
        self.assertIn("assets/readme/scene.py", stamp["inputs"])
        self.assertIn("assets/readme/yaslogist-mark.svg", stamp["inputs"])
        # Fonts change the letterforms, so they are inputs too.
        self.assertTrue(any(p.endswith(".ttf") for p in stamp["inputs"]))

    def test_probe_is_informational_not_a_gate(self) -> None:
        if importlib.util.find_spec("PIL") is None or importlib.util.find_spec("numpy") is None:
            self.skipTest("Pillow and NumPy are not installed")
        report = verify_assets.Report()
        verify_assets.probe_render(report, index=5)
        self.assertEqual(report.failures, [])
        self.assertTrue(any(c[0] in ("probe.render",) for c in report.checks + report.skips))

    def test_scene_constants_are_parsed(self) -> None:
        constants = verify_assets.scene_constants()
        self.assertEqual(constants["W,H"], (1920, 720))
        self.assertEqual(constants["FRAMES,DELAY"], (200, 50))


if __name__ == "__main__":
    unittest.main()

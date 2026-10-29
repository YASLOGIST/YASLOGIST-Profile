#!/usr/bin/env python3
"""Create the lightweight profile poster from the generated PNG master.

Run after build_hero.py. WebP metadata carries the source hash so the verifier
can detect a stale derivative without requiring byte-identical WebP encoders.
"""
from hashlib import sha256
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SOURCE = HERE / "yaslogist-hero.png"
OUTPUT = HERE / "yaslogist-hero.webp"


def main() -> None:
    digest = sha256(SOURCE.read_bytes()).hexdigest()
    xmp = (f'<x:xmpmeta xmlns:x="adobe:ns:meta/" '
           f'xmlns:yas="https://www.yaslogist.com/ns/" '
           f'yas:source-sha256="{digest}"/>').encode("utf-8")
    with Image.open(SOURCE) as image:
        image.convert("RGB").save(OUTPUT, "WEBP", quality=95, method=6, xmp=xmp)
    print(f"Wrote {OUTPUT.name} ({OUTPUT.stat().st_size:,} bytes)")


if __name__ == "__main__":
    main()

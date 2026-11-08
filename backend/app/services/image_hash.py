from __future__ import annotations

from pathlib import Path


def average_hash(path: Path) -> str | None:
    try:
        from PIL import Image
    except ImportError:
        return None
    if not path.exists():
        return None
    image = Image.open(path).convert("L").resize((8, 8))
    pixels = list(image.getdata())
    avg = sum(pixels) / len(pixels)
    return "".join("1" if pixel > avg else "0" for pixel in pixels)

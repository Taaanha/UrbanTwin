"""Known local landmarks with verified coordinates.

OpenStreetMap does not have every place people name in Noakhali, so this short list is kept by hand.
A citizen who types one of these names does not have to drop a pin: the report is placed here.
Add a place by appending a row (name, latitude, longitude); names are matched ignoring case and spacing.
"""

from __future__ import annotations

import re

LANDMARKS: list[dict] = [
    {"name": "Shonapur Zero Point", "lat": 22.825556, "lon": 91.101389},  # 22°49'32"N 91°6'5"E
]

_ALIASES = {"sonapur": "shonapur", "sonapurzeropoint": "shonapurzeropoint"}


def _norm(text: str) -> str:
    key = re.sub(r"[^a-z0-9]", "", text.lower())
    for wrong, right in _ALIASES.items():
        key = key.replace(wrong, right)
    return key


def find_landmark(text: str | None) -> dict | None:
    """The landmark whose name appears in `text` (or that contains it), or None. Needs at least 6 letters to avoid loose matches."""
    key = _norm(text or "")
    if len(key) < 6:
        return None
    for item in LANDMARKS:
        name = _norm(item["name"])
        if name in key or key in name:
            return item
    return None

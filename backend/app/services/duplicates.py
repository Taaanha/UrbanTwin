"""Transparent duplicate scoring. Humans still decide; nothing is merged here."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from difflib import SequenceMatcher
from math import asin, cos, radians, sin, sqrt

RELATED_CATEGORIES = {
    frozenset({"pothole", "damaged_road", "broken_sidewalk"}),
    frozenset({"blocked_drainage", "waterlogging", "flooding"}),
    frozenset({"garbage", "illegal_waste"}),
}

SEARCH_RADIUS_M = 120
TOKEN = re.compile(r"[a-zA-Z0-9\u0980-\u09FF]+")


@dataclass
class MatchReasons:
    distance_m: float
    distance_points: int
    category_points: int
    text_points: int
    recency_points: int
    image_points: int
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return (
            self.distance_points
            + self.category_points
            + self.text_points
            + self.recency_points
            + self.image_points
        )

    def suggested_label(self) -> str:
        score = self.total
        if score >= 70:
            return "possible_duplicate"
        if score >= 40:
            return "uncertain"
        return "weak"


def haversine_m(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371000.0
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlmb = radians(lon2 - lon1)
    a = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlmb / 2) ** 2
    return 2 * r * asin(sqrt(a))


def distance_points(metres: float) -> tuple[int, str]:
    if metres <= 25:
        return 50, "Within 25 m"
    if metres <= 50:
        return 35, "Within 50 m"
    if metres <= 80:
        return 20, "Within 80 m"
    if metres <= SEARCH_RADIUS_M:
        return 10, "Within 120 m"
    return 0, "Farther than 120 m"


def category_points(a: str, b: str) -> tuple[int, str]:
    if a == b:
        return 25, "Same category"
    pair = frozenset({a, b})
    if any(pair <= group for group in RELATED_CATEGORIES):
        return 12, "Related categories"
    return 0, "Different categories"


def text_points(a: str, b: str) -> tuple[int, str]:
    ratio = SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()
    tokens_a = set(TOKEN.findall(a.lower()))
    tokens_b = set(TOKEN.findall(b.lower()))
    if tokens_a and tokens_b:
        jaccard = len(tokens_a & tokens_b) / len(tokens_a | tokens_b)
    else:
        jaccard = 0.0
    points = int(round(20 * ratio + 10 * jaccard))
    return points, f"Text similarity {ratio:.2f}, token overlap {jaccard:.2f}"


def recency_points(hours_apart: float) -> tuple[int, str]:
    if hours_apart <= 24 * 14:
        return 5, "Reported within 14 days of each other"
    if hours_apart >= 24 * 180:
        return 0, "More than 6 months apart (historical, still not auto-merged)"
    return 2, "Reported months apart"


def hamming(a: str, b: str) -> int:
    return sum(ch1 != ch2 for ch1, ch2 in zip(a, b, strict=False)) + abs(len(a) - len(b))


def image_points(hash_a: str | None, hash_b: str | None) -> tuple[int, str]:
    if not hash_a or not hash_b:
        return 0, "No image comparison (missing photo on one or both reports)"
    distance = hamming(hash_a, hash_b)
    if distance <= 6:
        return 15, f"Images look similar (hash distance {distance})"
    if distance <= 12:
        return 6, f"Images somewhat similar (hash distance {distance})"
    return 0, f"Images look different (hash distance {distance})"


# Cosine thresholds are UNCALIBRATED starting points. Tune them on photo pairs you have
# labelled yourself (same defect / different defect) before trusting them.
EMBED_SAME = 0.85
EMBED_SIMILAR = 0.70


def image_points_embedding(similarity: float | None, model: str) -> tuple[int, str]:
    if similarity is None:
        return 0, "No image comparison (missing photo on one or both reports)"
    if similarity >= EMBED_SAME:
        return 15, f"Images very similar ({model} cosine {similarity:.2f})"
    if similarity >= EMBED_SIMILAR:
        return 6, f"Images somewhat similar ({model} cosine {similarity:.2f})"
    return 0, f"Images look different ({model} cosine {similarity:.2f})"


def score_pair(
    *,
    lon1: float,
    lat1: float,
    lon2: float,
    lat2: float,
    category1: str,
    category2: str,
    text1: str,
    text2: str,
    hours_apart: float,
    image_hash1: str | None = None,
    image_hash2: str | None = None,
    image_similarity: float | None = None,
    image_model: str | None = None,
) -> MatchReasons:
    metres = haversine_m(lon1, lat1, lon2, lat2)
    d_pts, d_note = distance_points(metres)
    c_pts, c_note = category_points(category1, category2)
    t_pts, t_note = text_points(text1, text2)
    r_pts, r_note = recency_points(hours_apart)
    if image_model is not None:
        i_pts, i_note = image_points_embedding(image_similarity, image_model)
    else:
        i_pts, i_note = image_points(image_hash1, image_hash2)
    return MatchReasons(
        distance_m=round(metres, 1),
        distance_points=d_pts,
        category_points=c_pts,
        text_points=t_pts,
        recency_points=r_pts,
        image_points=i_pts,
        notes=[d_note, c_note, t_note, r_note, i_note],
    )

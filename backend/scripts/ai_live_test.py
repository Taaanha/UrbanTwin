"""Live check of the AI pieces on real photos. Nothing is saved to the database.

Run from the backend folder (virtual environment active), with GEMINI_API_KEY in backend/.env:

    python -m scripts.ai_live_test ../datasets/test_photos

What it does for every .jpg/.jpeg/.png/.webp in the folder:
  1. average-hash and (if the AI extras are installed) DINOv2 embedding, then the similarity between every pair of photos
  2. the "second opinion" (category, severity, confidence, summary) from every configured provider (Gemini, local Ollama, Hugging Face vision model)

It prints what came back. Nothing here is an accuracy measurement: three photos cannot show that.
Compare each answer with what you can see in the photo yourself.
"""

from __future__ import annotations

import sys
from itertools import combinations
from pathlib import Path

from app.services import ai_opinion, image_embedding
from app.services.image_hash import average_hash

EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}


def hamming(a: str, b: str) -> int:
    """Number of differing bits between two average-hash bit strings (0 = identical, 64 = opposite)."""
    return sum(x != y for x, y in zip(a, b))


def main() -> None:
    folder = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("../datasets/test_photos")
    photos = sorted(p for p in folder.glob("*") if p.suffix.lower() in EXTENSIONS)
    if not photos:
        raise SystemExit(f"No photos found in {folder.resolve()}")
    print(f"{len(photos)} photos in {folder.resolve()}\n")

    print("== Duplicate-check signals ==")
    hashes, embeds = {}, {}
    for p in photos:
        hashes[p.name] = average_hash(p)
        got = image_embedding.embed_file(p)
        embeds[p.name] = got[1] if got else None
        print(f"{p.name}: hash={hashes[p.name]} embedding={'yes' if got else 'not available (install requirements-ai.txt)'}")
    for a, b in combinations([p.name for p in photos], 2):
        line = f"  {a} vs {b}: hash distance {hamming(hashes[a], hashes[b]) if hashes[a] and hashes[b] else '-'}"
        if embeds[a] and embeds[b]:
            line += f", embedding similarity {image_embedding.cosine(embeds[a], embeds[b]):.3f}"
        print(line)

    print("\n== Second opinions (every configured provider, side by side) ==")
    providers = ai_opinion.available_providers()
    active = [name for name, info in providers.items() if info["configured"]]
    if not active:
        print("No provider configured (GEMINI_API_KEY, OLLAMA_URL+OLLAMA_MODEL, or HF_API_TOKEN in backend/.env). Skipping.")
        return
    print("configured:", ", ".join(f"{n} ({providers[n]['model']})" for n in active))
    for p in photos:
        print(f"\n{p.name}")
        for name in active:
            try:
                result = ai_opinion.second_opinion(name, p)
            except ai_opinion.ProviderError as exc:
                print(f"  [{name}] FAILED: {exc}")
                continue
            print(
                f"  [{name}] problem={result.get('is_problem')} category={result.get('category')} severity={result.get('severity')} "
                f"model_score={result.get('confidence')} (self-reported, not calibrated) boxes={len(result.get('boxes') or [])}"
            )
            print(f"      {result.get('summary')}")
    print("\nReminder:", ai_opinion.WARNING)


if __name__ == "__main__":
    main()

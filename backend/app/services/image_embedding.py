"""Optional pretrained image embeddings (DINOv2 by default) for duplicate checks.

No training happens here. If torch/transformers are not installed, the model
cannot be downloaded, or EMBEDDING_MODEL=none, the code quietly falls back to
the 8x8 average hash, and the Investigator says which method was used.
Install the extras with:  pip install -r requirements-ai.txt
"""

from __future__ import annotations

import logging
from functools import lru_cache
from math import sqrt
from pathlib import Path
from typing import Protocol

from app.config import get_settings

log = logging.getLogger("urbantwin.embedding")


class Embedder(Protocol):
    model_name: str

    def embed(self, path: Path) -> list[float] | None: ...


class DinoEmbedder:
    """facebook/dinov2-* via Hugging Face transformers (Apache-2.0). CLS token, L2-normalised."""

    def __init__(self, model_name: str):
        import torch
        from transformers import AutoImageProcessor, AutoModel

        self.model_name = model_name
        self._torch = torch
        self._processor = AutoImageProcessor.from_pretrained(model_name)
        self._model = AutoModel.from_pretrained(model_name).eval()

    def embed(self, path: Path) -> list[float] | None:
        from PIL import Image

        with Image.open(path) as img:
            inputs = self._processor(images=img.convert("RGB"), return_tensors="pt")
        with self._torch.no_grad():
            vector = self._model(**inputs).last_hidden_state[:, 0, :][0]
        vector = vector / vector.norm()
        return vector.tolist()


_override: Embedder | None = None
_override_set = False


def set_embedder_for_tests(embedder: Embedder | None, *, active: bool = True) -> None:
    """Tests inject a stub (or None to force the hash fallback)."""
    global _override, _override_set
    _override, _override_set = embedder, active
    _embed_cached.cache_clear()


@lru_cache(maxsize=1)
def _load_default() -> Embedder | None:
    name = (get_settings().embedding_model or "none").strip()
    if name.lower() == "none":
        return None
    try:
        return DinoEmbedder(name)
    except Exception as exc:  # noqa: BLE001 - any failure means "use the hash fallback"
        log.warning("Image embeddings unavailable (%s). Falling back to average hash.", exc)
        return None


def get_embedder() -> Embedder | None:
    return _override if _override_set else _load_default()


@lru_cache(maxsize=512)
def _embed_cached(path_str: str, model_name: str) -> tuple[float, ...] | None:
    embedder = get_embedder()
    if embedder is None or embedder.model_name != model_name:
        return None
    try:
        vector = embedder.embed(Path(path_str))
    except Exception as exc:  # noqa: BLE001
        log.warning("Embedding failed for %s: %s", path_str, exc)
        return None
    return tuple(vector) if vector else None


def embed_file(path: Path) -> tuple[str, tuple[float, ...]] | None:
    """(model_name, vector) or None if embeddings are unavailable for this file."""
    embedder = get_embedder()
    if embedder is None or not path.exists():
        return None
    vector = _embed_cached(str(path), embedder.model_name)
    return (embedder.model_name, vector) if vector else None


def cosine(a: tuple[float, ...], b: tuple[float, ...]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = sqrt(sum(x * x for x in a))
    nb = sqrt(sum(y * y for y in b))
    return dot / (na * nb) if na and nb else 0.0

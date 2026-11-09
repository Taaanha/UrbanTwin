"""Serve the built React app from the API server (used in the Docker image, one deployable unit)."""

from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles


def mount_frontend(app: FastAPI, dist: str) -> bool:
    """Add static asset serving plus a single-page-app fallback. Returns False when there is nothing to serve.

    Must be called after every API route is registered. Paths under /api never fall back to index.html.
    """
    root = Path(dist).resolve() if dist else None
    if root is None or not (root / "index.html").is_file():
        return False
    if (root / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=root / "assets"), name="assets")

    @app.get("/{full_path:path}", include_in_schema=False)
    def spa(full_path: str):
        if full_path == "api" or full_path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not found.")
        candidate = (root / full_path).resolve()
        if full_path and candidate.is_file() and candidate.is_relative_to(root):
            return FileResponse(candidate)
        return FileResponse(root / "index.html")

    return True

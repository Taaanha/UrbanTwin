"""List the Gemini models your API key can call with generateContent (names change over time).

    python -m scripts.list_gemini_models

Then put one of the printed names in backend/.env as GEMINI_MODEL=<name>. The key is never printed.
"""

from __future__ import annotations

import requests

from app.config import get_settings


def main() -> None:
    s = get_settings()
    if not s.gemini_api_key:
        raise SystemExit("GEMINI_API_KEY is not set in backend/.env")
    response = requests.get(
        "https://generativelanguage.googleapis.com/v1beta/models?pageSize=200",
        headers={"x-goog-api-key": s.gemini_api_key},
        timeout=20,
    )
    if response.status_code != 200:
        raise SystemExit(f"HTTP {response.status_code}: {response.text[:300]}")
    models = [m for m in response.json().get("models", []) if "generateContent" in m.get("supportedGenerationMethods", [])]
    print(f"Configured model: {s.gemini_model}")
    print(f"{len(models)} models support generateContent:")
    for m in models:
        print(" ", m["name"].removeprefix("models/"), "-", m.get("displayName", ""))


if __name__ == "__main__":
    main()

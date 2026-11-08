# Feature status (what is real, simplified, or missing)

| Area | Status | Notes |
|------|--------|-------|
| Interactive map, OSM roads/buildings/water | Real | OSM is incomplete; no official Paurashava boundary |
| Wards | **Demo grid** | Not official wards |
| Citizen reports, photos, GPS, tracking ID, EN/BN form | Real | GPS is the browser location or a map pin; EXIF GPS not read |
| Report filters and status | Real | |
| Duplicate detection | Real | distance/category/text/time + image similarity: pretrained DINOv2 embeddings (cosine) when `requirements-ai.txt` is installed, else 8x8 average hash. Cosine thresholds are uncalibrated; CPU-tested only with a stub model in this build |
| Human verification + history | Real | |
| Road/drain/water/ward linking, recurrence, graph | Real, simple | Straight-line nearest feature; no network routing. OSM drains absent -> demo drains |
| Cost estimation | Simplified | Assumed quantities, placeholder rates, no road length/width model |
| Budget planning | Real | 3 greedy + OR-Tools optimal; scores are heuristics |
| Projects, progress, completion evidence, inspections | Real | Contractor is optional free text |
| Recurrence screening | Real, simple | Distance + time + documentation checks; no rainfall |
| Green-space accessibility scenarios | Real, simple | Straight-line distance, building centres, no population |
| Waste-collection and drainage scenarios | **Not built** | Budget scenarios cover repairs only |
| Staff access | Simplified | One shared token; names in audit log are self-declared |
| Audit log | Real | Reports status, verification, planner rates, projects, simulation runs |
| Migrations | Real | Alembic baseline |
| AI second opinion (Gemini / Hugging Face API) | Built, **untested live** | Staff button; photo sent with EXIF removed; output is an unverified candidate; needs your own keys; tested only with mocked responses (sandbox had no access to either service) |
| Local YOLO detector | **Not built** | Optional, see `docs/CLAUDE_CODE_NEXT_STEPS.md` |
| Segmentation / satellite change detection / CHIRPS / SRTM | **Not built** | By design: no suitable data or evaluation here |
| Deployment | Local only | Documented for localhost |
| Browser UI tests | **None** | Type-check and build only; click through `DEMO_SCRIPT.md` |

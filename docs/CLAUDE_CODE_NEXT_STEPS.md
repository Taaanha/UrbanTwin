# Next steps for Claude Code (run locally in D:\Urbantwin)

Open a terminal in `D:\Urbantwin` and start Claude Code. Paste the prompts below one at a time. Claude Code can run your Windows PostgreSQL, the dev servers, `pytest`, and git, which the cloud session could not.

## Prompt 1 - first run and fixes (do this first)

```
Read README.md and docs/ARCHITECTURE.md. The project was extended in a cloud sandbox
(phases 6-8, staff auth, Alembic, demo seed, image embeddings) and has NOT yet run on
this Windows machine. Please:
1. Activate backend\.venv, run `pip install -r requirements.txt`, then `alembic upgrade head`
   against my urbantwin database (port 5433). Do not drop or delete any data.
2. Run `python -m pytest -q` in backend and fix any failure with the smallest change.
3. Run `npm install` and `npm run build` in frontend and fix any error.
4. Start the backend (uvicorn) and frontend (npm run dev), open http://localhost:5173,
   log in as staff with STAFF_TOKEN from backend\.env, and click through every page in
   docs/DEMO_SCRIPT.md. Report anything broken, fix it, and re-test.
5. Do not claim anything works unless you ran it. Then show me `git status` and propose
   commits in logical chunks (do not commit until I say yes).
```

## Prompt 2 - turn on and calibrate DINOv2 image similarity

The code is already in `backend/app/services/image_embedding.py` and is tested only with a stub model, because the cloud sandbox could not download model weights.

```
1. In backend\.venv run: pip install torch --index-url https://download.pytorch.org/whl/cpu
   then: pip install -r requirements-ai.txt
2. Start the API with EMBEDDING_MODEL=facebook/dinov2-small and confirm the first
   Investigator inspect call works (model downloads once, ~90 MB). If it fails, show the
   warning logged by `urbantwin.embedding` and fix it.
3. Calibrate: create a folder datasets\annotations\image_pairs with two subfolders,
   `same` and `different`, containing pairs of photos (I will supply them; use 20+ pairs
   each, ideally my own photos of Noakhali roads). Write scripts\calibrate_embeddings.py
   that prints the cosine similarity for each pair, the best threshold separating the two
   groups, and precision/recall at the current constants EMBED_SAME=0.85 and
   EMBED_SIMILAR=0.70 in app/services/duplicates.py. Only change those constants if the
   measured data supports it, and tell me the numbers. Never invent accuracy figures.
4. Add a test that is skipped automatically when torch is not installed.
```

## Prompt 2b - test the AI second-opinion API live

The code (`backend/app/services/ai_opinion.py`, route `POST /api/investigator/reports/{id}/ai-opinion`) was only tested with mocked responses, because the cloud sandbox could not reach Google or Hugging Face.

```
1. Put GEMINI_API_KEY (and optionally HF_API_TOKEN + HF_DETECTION_MODEL) in backend\.env.
   I will choose the Hugging Face model: first tell me which object-detection models are
   currently available on the HF Inference API, their licences, and whether any is trained
   on road damage. Do not pick one without telling me. Also check the current Gemini model
   name in Google's docs and update GEMINI_MODEL if "gemini-2.5-flash" is retired.
2. Verify the request/response formats against the providers' current documentation (URL,
   headers, JSON shape). Fix anything that changed, keeping the output sanitising intact.
3. Try it on 5 real photos from the Investigator page. Report what came back, including
   failures and obviously wrong answers. Do not report accuracy figures.
4. Confirm the key never appears in logs, responses or the audit log.
```

## Prompt 3 - optional LOCAL pothole detection (YOLO). Check licence and data FIRST

```
Goal: an OPTIONAL "AI suggestion" that proposes pothole/road-damage boxes on an uploaded
photo. It must never create a verified issue; output is a candidate shown to staff.

Before writing code, research and tell me (with links):
a) Licences: Ultralytics YOLO (v8/11) is AGPL-3.0. Explain what that means for a university
   demo vs. distributing the app, and list permissively licensed alternatives (e.g. RT-DETR
   or YOLO variants under Apache/MIT) that could replace it.
b) Datasets: whether RDD2022 (or any public road-damage dataset) contains Bangladesh roads,
   its licence, and download size. If no Bangladeshi data exists, say so plainly.
c) Whether a ready-made pretrained road-damage checkpoint exists with a licence I can use.
Wait for my decision after reporting a-c.

Then, if I approve:
- Add backend/app/services/damage_detection.py with a pluggable detector (same pattern as
  image_embedding.py: lazy import, graceful fallback to "unavailable").
- Add POST /api/investigator/reports/{tracking_id}/detect (staff only) returning boxes,
  confidence, model name, and the text "AI candidate - not verified". Do NOT change report
  status or create issues from it.
- Show the boxes on the Investigator page with the same warning.
- Evaluate on photos I label myself (put them in datasets\annotations\damage_eval). Report
  measured precision/recall and state clearly that it is on a small, local sample. If I
  have no labelled photos, say the accuracy is unmeasured; do not quote benchmark numbers
  from the dataset paper as if they applied to Noakhali.
- Domain shift warning in the UI: models trained on other countries' roads may miss or
  hallucinate damage on Noakhali roads.
- Add tests (skipped when the model package is absent) and update docs/FEATURE_STATUS.md.
```

## Rules to keep (from the original brief)
No fabricated data or accuracy; synthetic data stays labelled `is_demo`; AI output is a candidate until a human verifies; never imply wrongdoing by a contractor or official; commit after each milestone.

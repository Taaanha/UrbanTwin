# Lab demonstration script (about 12 minutes)

**Before the exam:** database running, `alembic upgrade head`, OSM import done, `python scripts\seed_demo.py --reset`, `STAFF_TOKEN` set, API on :8000, `npm run dev` on :5173. Run `python -m pytest -q` once so you can say "29 tests passed". Check internet for the base map tiles.

## 0. Framing (30 s)
"UrbanTwin connects reporting, verification, infrastructure context, planning, project tracking and what-if simulation in one database. Everything labelled DEMO is synthetic."

## 1. Citizen report (City Monitor) - `/`
1. Switch to Bangla with the language button, back to English.
2. Pick *Pothole*, type a description, drop a pin (or the location button), attach a photo, submit.
3. Copy the tracking ID, open `/track`, paste it: status is **submitted** and the page says it is *not yet a verified issue*.

## 2. Staff login + overview - `/overview`
Click **Staff login**, enter your name and token. Show the live counts and the DEMO banner. Say: "These are database counts, not hard-coded numbers."

## 3. Monitor - `/dashboard`
Toggle layers (roads, buildings, water, drains, wards), filter by category/severity/status, click a report marker. Mention wards are a demo grid.

## 4. Investigator - `/investigator`
1. Open your new report. Show candidate matches with the **score breakdown** (distance, category, text, recency, image hash).
2. Open the seeded garbage pair: label *possible_duplicate*. Choose **possible duplicate**, link it, add a note.
3. Open your own report, choose **new candidate issue**. Say: "Nothing merged automatically; both originals are preserved; the decision is in the history."

## 5. Intelligence - `/intelligence`
Click **Recompute spatial links**. Open an issue: nearest road, drain (demo), ward, with distances and the *correlation, not cause* disclaimer. Show the recurrence list (ISS-DEMO pothole pair, 55 days apart) and the relationship graph.

## 6. Planner - `/planner`
**Draft interventions**, open one: quantity, indicative low/mid/high cost, assumptions. Edit a unit rate (it is audited). Click **Compare budget packs**: show the greedy methods vs **optimal_knapsack** (OR-Tools).

## 7. Accountability - `/accountability`
1. Open `PRJ-DEMO-...` (completed 30 days ago): lifecycle chain from issue to project to recurrence, and the screening box **Worth independent review** because a related issue appeared 27 days after completion.
2. Read the disclaimer aloud: "a screening signal, not an allegation".
3. Create a project from one of your interventions, add a 40% update, try to complete without a photo (rejected), complete with a photo, add an *independent* inspection: the issue turns `resolved_verified`.

## 8. Simulation - `/simulation`
Green tab: baseline access percentage, run 10 sites x 25 trees, show before/after per ward and the map. Open "Assumptions and limits". Budget tab: compare 30k / 100k / 300k.

## 9. Audit - `/admin`
Show the dataset register (source, licence, limitations, DEMO flags) and the audit log with your name against each action.

## If something goes wrong
* Staff pages say "login required": re-enter the token.
* Blank map: no internet for tiles; the layers still load.
* Empty simulation: run `import_osm_green.py` or the demo seed.
* Health check: http://127.0.0.1:8000/api/health

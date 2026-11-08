# Likely examiner questions, with honest answers

**What problem does UrbanTwin solve?** Municipal problems are reported, fixed and forgotten in separate places. UrbanTwin keeps one traceable chain: report, verified issue, spatial context, proposed fix with cost, approved project, inspection, recurrence.

**Why this architecture?** A modular monolith (FastAPI + PostGIS + React) is easiest to run, debug and demonstrate on one laptop with no paid services. Modules share a database, so the lifecycle is preserved by foreign keys instead of network calls.

**Why PostgreSQL and PostGIS?** Spatial types, GiST indexes and distance/containment functions are needed to snap issues to roads and wards; relational integrity protects the report -> project chain; JSONB stores scores and scenario results.

**How does duplicate detection work?** `services/duplicates.py` scores each nearby pair (within 120 m) in points (maximum 125): distance up to 50, same/related category 25/12, text similarity up to 30 (sequence ratio + token overlap), time 5, image similarity up to 15 (DINOv2 cosine, or average hash as fallback). 70+ is *possible_duplicate*, 40+ *uncertain*. It is only a suggestion; a staff member decides, originals are kept, and the reasons are stored with the decision.

**Which AI models are used?** Image similarity uses a pretrained DINOv2 model (Apache-2.0, no training, CPU) turned into embeddings and compared by cosine similarity; if it is not installed the system falls back to a simple average hash and says so on screen. The similarity thresholds are starting values, not calibrated. No detector (YOLO) is built yet: any future detection would be a candidate until a person verifies it, and accuracy would only be quoted if measured on photos we labelled ourselves.

**How does it connect roads and drainage?** After verification, each issue is snapped to the nearest road (60 m), drain (80 m), water body (80 m) and containing ward using PostGIS distances. Issues sharing a road or drain, or near each other, get `IssueRelation` rows. It is spatial **correlation**; the UI says so. OSM has no drains here, so drain links use clearly labelled demo drains.

**How is cost estimated?** quantity x unit rate, split 40/40/10 labour/materials/equipment, +10% contingency, shown as a +/-25% range. Quantities are assumed per category (e.g. a pothole is 4 m2) and rates are placeholders editable in the UI. They are **not** PWD/LGED rates. Road length/width are not used yet because OSM road widths are mostly absent.

**How does budget optimisation work?** Three greedy heuristics (value per taka, severity first, ward-balanced) and an exact 0/1 knapsack in OR-Tools CP-SAT that maximises total priority score within the budget. Scores are lab heuristics (severity, category weight, recurrence flag, same-road cluster). Population and equity beyond ward balance are not modelled.

**How is project completion verified?** It is not "verified" by software. Completion needs a photo; an **independent** inspection with outcome *meets specification* marks the issue `resolved_verified`; anything else leaves it `repair_reported` or `repair_disputed`. The app records evidence and flags gaps.

**What does the recurrence screen do, and what does it not do?** It flags a completed project when a related issue is verified within 40 m after completion (flagged as faster than the lab threshold of 90 days), when completion evidence is missing, when spending exceeds the approved budget by more than 10%, or when an independent inspection failed. It never says why. Rainfall data is not loaded, so weather is not examined. It does not allege wrongdoing.

**AI prediction vs verified issue?** A report (or any model output) is a candidate. It becomes an `Issue` only through a human `Verification`. They are separate tables and the API labels each record type.

**Limits of satellite imagery?** Sentinel-2 (10 m) and Landsat (30 m) cannot see potholes, and SRTM (~30 m) cannot show drainage slopes. CHIRPS is regional rainfall. None are integrated in this build, and none should be presented as detecting small defects.

**How do the six modules communicate?** Through the shared database and service calls (see `ARCHITECTURE.md`): verification triggers intelligence refresh and recurrence checks; the planner reads intelligence relations; projects reference interventions and issues; simulation reads the planner's candidates and rates; every staff write goes to the audit log.

**Security?** Staff routes need a token (constant-time compare), uploads are validated by file signature and size, files get random names, secrets are in `.env`, input is validated with Pydantic, tests cover 401s. Weakness to admit: one shared token, no HTTPS, no per-user roles yet.

**Was synthetic data used?** Yes, only through `seed_demo.py`: every row is flagged `is_demo` and shown as DEMO. Roads/buildings/water are real OSM.

**Do you send citizen photos to external AI services?** Only when a staff member clicks "Ask AI" on one report, and only if an API key is configured. The photo is re-encoded without EXIF/GPS and downsized; the action is written to the audit log; the citizen form carries a notice. The answer is shown as "AI candidate - not verified" and cannot change a report or create an issue. Without keys the feature is off and nothing leaves the machine.

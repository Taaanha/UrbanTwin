from fastapi.testclient import TestClient
from geoalchemy2.shape import from_shape
from shapely.geometry import box

from app.database import SessionLocal
from app.main import app
from app.models.geo import Building
from app.models.simulation import GreenSpace
from tests.helpers import new_issue

client = TestClient(app)


def _seed_buildings(step=0.0015):
    """~100 tiny buildings on a grid inside ward 1's neighbourhood (north-west of the study area)."""
    with SessionLocal() as db:
        for i in range(10):
            for j in range(10):
                x, y = 91.078 + i * step, 22.887 - j * step
                db.add(
                    Building(
                        osm_id=1000 + i * 10 + j,
                        geom=from_shape(box(x, y, x + 0.0002, y + 0.0002), srid=4326),
                        properties={},
                    )
                )
        db.commit()


def _seed_green():
    with SessionLocal() as db:
        db.add(
            GreenSpace(
                name="Test park",
                kind="park",
                geom=from_shape(box(91.0775, 22.8865, 91.0795, 22.8885), srid=4326),
                is_demo=True,
            )
        )
        db.commit()


def test_baseline_warns_when_no_green_data_is_loaded():
    _seed_buildings()
    body = client.get("/api/simulation/green/baseline").json()
    assert body["data_warning"] and "No green-space polygons" in body["data_warning"]
    assert body["city"]["buildings"] == 100
    assert body["city"]["access_pct"] == 0.0
    assert any("demonstration grid" in a for a in body["assumptions"])


def test_gap_fill_scenario_improves_access_and_states_its_assumptions():
    _seed_buildings()
    _seed_green()
    before = client.get("/api/simulation/green/baseline").json()
    assert 0 < before["city"]["access_pct"] < 100
    run = client.post("/api/simulation/green", json={"name": "Pocket parks", "sites": 3, "trees_per_site": 25})
    assert run.status_code == 200, run.text
    result = run.json()["result"]
    assert result["city_after"]["access_pct"] > result["city_before"]["access_pct"]
    assert result["total_trees"] == 75
    assert len(result["sites"]) <= 3 and all(s["newly_covered_buildings"] > 0 for s in result["sites"])
    assert result["city_after"]["green_m2"] > result["city_before"]["green_m2"]
    assert "not forecasts" in result["disclaimer"].lower()
    assert "straight line" in run.json()["assumptions"]
    assert result["green_is_demo"] is True

    again = client.post("/api/simulation/green", json={"name": "Pocket parks", "sites": 3, "trees_per_site": 25}).json()
    assert again["result"]["sites"] == result["sites"]  # deterministic
    saved = client.get(f"/api/simulation/scenarios/{run.json()['public_id']}")
    assert saved.status_code == 200
    assert len(client.get("/api/simulation/scenarios").json()["items"]) == 2


def test_manual_sites_and_validation():
    _seed_buildings()
    _seed_green()
    ok = client.post("/api/simulation/green", json={"strategy": "manual", "manual_sites": [[91.09, 22.88]]})
    assert ok.status_code == 200, ok.text
    assert len(ok.json()["result"]["sites"]) == 1
    assert client.post("/api/simulation/green", json={"strategy": "manual"}).status_code == 400
    assert client.post("/api/simulation/green", json={"strategy": "manual", "manual_sites": [[0, 0]]}).status_code == 400
    assert client.post("/api/simulation/green", json={"sites": 0}).status_code == 422


def test_budget_scenarios_compare_methods_and_optimal_is_at_least_greedy():
    for k in range(4):
        new_issue(client, f"Pothole number {k} on the test road.", lon=str(91.095 + k * 0.002), severity=["low", "medium", "high", "critical"][k])
    body = client.post("/api/simulation/budget", json={"budgets_bdt": [20_000, 60_000, 10_000_000]}).json()
    assert "does not approve" in body["disclaimer"]
    assert body["interventions_considered"] == 4
    for run in body["runs"]:
        methods = run["methods"]
        assert set(methods) == {"greedy_value", "greedy_severity", "greedy_equity", "optimal_knapsack"}
        best = methods["optimal_knapsack"]
        for other in methods.values():
            assert best["total_priority_score"] >= other["total_priority_score"]
            assert other["spent_bdt"] <= run["budget_bdt"] + 1e-6
    assert body["runs"][2]["methods"]["optimal_knapsack"]["included_count"] == 4
    assert client.post("/api/simulation/budget", json={"budgets_bdt": [-5]}).status_code == 400


def test_green_result_carries_an_uncertainty_range_that_brackets_the_central_value():
    _seed_buildings()
    _seed_green()
    result = client.post("/api/simulation/green", json={"name": "range", "sites": 3, "trees_per_site": 25}).json()["result"]
    u = result["uncertainty"]
    pct = u["access_after_pct"]
    assert pct["low"] <= pct["central"] <= pct["high"]
    assert pct["central"] == result["city_after"]["access_pct"]
    assert [r["factor"] for r in u["rows"]] == [0.75, 1.0, 1.25]
    assert "Tree survival and canopy growth" in u["not_modelled"]

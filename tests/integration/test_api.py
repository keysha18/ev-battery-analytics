"""API contre la vraie base (marts remplis par make dbt-build + make analyze), avec le rôle api_ro."""

import os

import psycopg
import pytest
from fastapi.testclient import TestClient

from src.api.main import app

pytestmark = pytest.mark.integration


@pytest.fixture(scope="module")
def client():
    if "API_RO_USER" not in os.environ:
        pytest.skip("variables .env absentes (lancer via make test)")
    try:
        with TestClient(app) as c:
            if c.get("/health").status_code != 200:
                pytest.skip("tables analytiques absentes (make dbt-build && make analyze)")
            yield c
    except Exception as exc:
        if isinstance(exc, pytest.skip.Exception):
            raise
        pytest.skip(f"API/base indisponible : {exc}")


def test_health(client):
    assert client.get("/health").json() == {"status": "ok", "database": "ok"}


# --- liste -----------------------------------------------------------------------------------------

def test_list_all_batteries(client):
    r = client.get("/batteries", params={"limit": 100}).json()
    assert r["total"] == 34 and len(r["items"]) == 34
    assert [b["cell_id"] for b in r["items"]] == sorted(b["cell_id"] for b in r["items"])


def test_list_pagination(client):
    r = client.get("/batteries", params={"limit": 5, "offset": 30}).json()
    assert r["total"] == 34 and len(r["items"]) == 4


def test_list_filter_profile(client):
    r = client.get("/batteries", params={"profile": "multi_level", "limit": 100}).json()
    # B0038-40 et B0041-44 (à ne pas confondre avec les 6 cellules à conditions mixtes dans leurs données)
    assert {b["cell_id"] for b in r["items"]} == {f"B00{n}" for n in (38, 39, 40, 41, 42, 43, 44)}
    assert {b["discharge_profile"] for b in r["items"]} == {"multi_level"}


def test_list_filter_combination(client):
    r = client.get("/batteries", params={"forecast_status": "observed", "temp_c": 24, "limit": 100}).json()
    assert {b["cell_id"] for b in r["items"]} == {"B0005", "B0006", "B0018", "B0033", "B0034"}


@pytest.mark.parametrize("params", [{"profile": "inconnu"}, {"limit": 0}, {"limit": 101}, {"offset": -1}])
def test_list_rejects_invalid_parameters(client, params):
    assert client.get("/batteries", params=params).status_code == 422


# --- détail ----------------------------------------------------------------------------------------

def test_battery_detail(client):
    b = client.get("/batteries/B0005").json()
    assert b["nominal_capacity_ah"] == 2.0
    assert b["forecast_status"] == "observed" and b["observed_eol_age_index"] == 125
    assert b["eol_basis"] == "nasa_absolute" and b["eol_threshold_ah"] == 1.4
    assert b["has_full_series"] is True


def test_unknown_battery_is_404(client):
    for path in ("/batteries/B9999", "/batteries/B9999/soh", "/batteries/B9999/cycles", "/batteries/B9999/rul"):
        assert client.get(path).status_code == 404


@pytest.mark.parametrize("cell_id", ["abc", "B05", "B0005; drop table x", "b0005"])
def test_malformed_cell_id_is_422(client, cell_id):
    assert client.get(f"/batteries/{cell_id}").status_code == 422


def test_unreliable_fade_is_hidden_when_insufficient(client):
    b = client.get("/batteries/B0052").json()
    assert b["fade_estimate_quality"] == "insufficient"
    assert b["fade_pct_per_100_discharges"] is None  # -712 % sur 4 points : absurde, non exposé


# --- SOH et cycles ----------------------------------------------------------------------------------

def test_soh_series(client):
    s = client.get("/batteries/B0005/soh").json()
    assert len(s["points"]) == 168
    assert s["reference"]["nominal_capacity_ah"] == 2.0
    assert [p["age_index"] for p in s["points"]] == list(range(1, 169))


def test_soh_post_peak_only(client):
    full = client.get("/batteries/B0007/soh").json()["points"]
    post = client.get("/batteries/B0007/soh", params={"post_peak_only": True}).json()["points"]
    assert len(post) < len(full)
    assert all(p["is_post_peak"] for p in post)


def test_cycles_include_invalid_by_default(client):
    allc = client.get("/batteries/B0052/cycles", params={"limit": 1000}).json()
    valid = client.get("/batteries/B0052/cycles", params={"limit": 1000, "valid_only": True}).json()
    assert allc["total"] == 25 and valid["total"] == 4
    assert {c["invalid_reason"] for c in allc["items"] if not c["is_valid_capacity"]} == {"missing"}


def test_cycles_pagination(client):
    p = client.get("/batteries/B0005/cycles", params={"limit": 10, "offset": 160}).json()
    assert p["total"] == 168 and len(p["items"]) == 8


# --- fin de vie : ce qui est publié, et avec quelles réserves ---------------------------------------

def test_rul_observed_has_no_prediction(client):
    r = client.get("/batteries/B0005/rul").json()
    assert r["status"] == "observed" and r["prediction"] is None
    assert r["observed_eol_age_index"] == 125
    assert r["knee"] is not None and r["caveats"]


def test_rul_extrapolated_carries_prediction_and_caveats(client):
    r = client.get("/batteries/B0043/rul").json()
    assert r["status"] == "extrapolated"
    p = r["prediction"]
    assert p["interval_low"] <= p["eol_age_index"] and p["rul_discharges"] >= 0
    text = " ".join(r["caveats"])
    assert "Backtest" in text and "trop étroit" in text and "trop tardive" in text and "trop précoce" in text


def test_rul_unreliable_publishes_no_number(client):
    r = client.get("/batteries/B0038/rul").json()
    assert r["status"] == "unreliable_forecast" and r["prediction"] is None


def test_rul_without_threshold(client):
    r = client.get("/batteries/B0025/rul").json()
    assert r["status"] == "no_threshold" and r["prediction"] is None and r["eol_threshold_ah"] is None


def test_every_battery_never_exposes_prediction_unless_extrapolated(client):
    for b in client.get("/batteries", params={"limit": 100}).json()["items"]:
        r = client.get(f"/batteries/{b['cell_id']}/rul").json()
        assert (r["prediction"] is not None) == (r["status"] == "extrapolated"), b["cell_id"]
        if r["prediction"]:
            assert r["prediction"]["rul_discharges"] >= 0


# --- synthèse et sécurité ---------------------------------------------------------------------------

def test_fleet_summary(client):
    s = client.get("/fleet/summary").json()
    assert s["n_batteries"] == 34
    assert sum(x["n"] for x in s["by_forecast_status"]) == 34
    assert sum(x["n"] for x in s["by_fade_quality"]) == 34
    assert [b["observed_fraction"] for b in s["backtest"]] == [0.5, 0.7, 0.9]
    assert all(0 <= b["interval_coverage"] <= 1 for b in s["backtest"])
    assert s["notes"]


def test_fleet_backtest_rows_match_summary(client):
    rows = client.get("/fleet/backtest").json()
    summary = client.get("/fleet/summary").json()["backtest"]
    assert len(rows) == 18 and sum(b["n_cells"] for b in summary) == 18
    assert all(r["error_discharges"] == pytest.approx(r["predicted_eol_age_index"] - r["actual_eol_age_index"])
               for r in rows)


def test_api_connection_is_read_only(client):
    with client.app.state.pool.connection() as conn, pytest.raises(psycopg.Error):
        conn.execute("create table marts.should_not_exist (i int)")
    with client.app.state.pool.connection() as conn, pytest.raises(psycopg.Error):
        conn.execute("delete from marts.dim_battery")


def test_openapi_documents_all_routes(client):
    paths = client.get("/openapi.json").json()["paths"]
    assert {"/health", "/batteries", "/batteries/{cell_id}", "/batteries/{cell_id}/soh",
            "/batteries/{cell_id}/cycles", "/batteries/{cell_id}/rul", "/fleet/summary"} <= set(paths)

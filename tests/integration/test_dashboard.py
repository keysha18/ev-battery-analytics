"""Fait tourner l'application Streamlit entière contre la vraie API (rôle api_ro, vraies données)."""

import os
from pathlib import Path

import pytest
import streamlit as st
from fastapi.testclient import TestClient
from streamlit.testing.v1 import AppTest

from dashboard import client as dash_client
from src.api.main import app as api_app

pytestmark = pytest.mark.integration
APP = str(Path(__file__).resolve().parents[2] / "dashboard" / "app.py")  # from_file résout les chemins relatifs depuis ce fichier


@pytest.fixture
def run_app(monkeypatch):
    if "API_RO_USER" not in os.environ:
        pytest.skip("variables .env absentes (lancer via make test)")
    try:
        api = TestClient(api_app)
        api.__enter__()
    except Exception as exc:  # noqa: BLE001 - base injoignable => on saute
        pytest.skip(f"API/base indisponible : {exc}")
    if api.get("/health").status_code != 200:
        api.__exit__(None, None, None)
        pytest.skip("tables analytiques absentes (make dbt-build && make analyze)")
    st.cache_resource.clear()
    st.cache_data.clear()
    monkeypatch.setattr(dash_client, "make_client", lambda: api)
    yield lambda: AppTest.from_file(APP, default_timeout=60).run()
    api.__exit__(None, None, None)
    st.cache_resource.clear()
    st.cache_data.clear()


def texts(at):
    return " ".join(m.value for m in at.markdown)


def test_app_renders_overview_without_error(run_app):
    at = run_app()
    assert not at.exception
    assert len(at.tabs) == 4
    assert "6 / 22" in texts(at)  # cellules ayant franchi leur seuil de fin de vie


def test_overview_filters_scope_the_table(run_app):
    at = run_app()
    at.selectbox(key="ov_profile").select("square_wave").run()
    assert not at.exception
    assert at.selectbox(key="ov_profile").value == "square_wave"


def test_cell_view_for_observed_and_extrapolated_cells(run_app):
    at = run_app()
    at.selectbox(key="cell_pick").select("B0005").run()
    assert not at.exception and "Fin de vie observée" in texts(at)
    at.selectbox(key="cell_pick").select("B0043").run()
    assert not at.exception and "Prévision par extrapolation" in texts(at)


def test_cell_view_for_refused_forecast_shows_no_number(run_app):
    at = run_app()
    at.selectbox(key="cell_pick").select("B0038").run()
    assert not at.exception
    body = texts(at)
    assert "Prévision refusée" in body and "non publiée" in body


def test_cell_view_every_cell_and_unit_renders(run_app):
    at = run_app()
    for cell in at.selectbox(key="cell_pick").options:
        at.selectbox(key="cell_pick").select(cell.split(" ")[0] if " · " in cell else cell).run()
        assert not at.exception, cell


def test_compare_view_keeps_colors_when_a_cell_is_removed(run_app):
    at = run_app()
    before = dict(at.session_state["cmp_slots"]) if "cmp_slots" in at.session_state else None
    at.multiselect(key="cmp_cells").set_value(["B0005", "B0006", "B0018"]).run()
    assert not at.exception
    slots = dict(at.session_state["cmp_slots"])
    at.multiselect(key="cmp_cells").set_value(["B0006", "B0018"]).run()
    assert not at.exception
    after = dict(at.session_state["cmp_slots"])
    assert after == {c: slots[c] for c in ("B0006", "B0018")}, (before, slots, after)


def test_trust_view_states_the_backtest_limits(run_app):
    at = run_app()
    body = texts(at)
    assert "Intervalles justes" in body and "effectif très réduit" in body

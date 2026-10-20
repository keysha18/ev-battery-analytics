"""Le dashboard ne lit que l'API : aucun accès direct à la base."""

import os

import httpx
import streamlit as st

API_URL = os.environ.get("API_URL", "http://localhost:8000")


def make_client() -> httpx.Client:
    return httpx.Client(base_url=API_URL, timeout=10.0)


@st.cache_resource
def _client() -> httpx.Client:
    return make_client()


@st.cache_data(ttl=60, show_spinner=False)
def _get(path: str, params: tuple = ()):
    r = _client().get(path, params=dict(params))
    r.raise_for_status()
    return r.json()


def batteries() -> list[dict]:
    return _get("/batteries", (("limit", 100),))["items"]


def battery(cell_id: str) -> dict:
    return _get(f"/batteries/{cell_id}")


def soh(cell_id: str) -> dict:
    return _get(f"/batteries/{cell_id}/soh")


def rul(cell_id: str) -> dict:
    return _get(f"/batteries/{cell_id}/rul")


def fleet_summary() -> dict:
    return _get("/fleet/summary")


def fleet_backtest() -> list[dict]:
    return _get("/fleet/backtest")

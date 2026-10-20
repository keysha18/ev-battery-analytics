"""Lecture des .mat NASA et réduction en lignes prêtes pour la base. Aucune I/O base ici."""

from collections.abc import Iterator
from datetime import datetime, timedelta
from math import isnan
from pathlib import Path

import numpy as np
from scipy.io import loadmat

CYCLE_TYPES = ("charge", "discharge", "impedance")


def datevec_to_datetime(vec) -> datetime:
    """Date vector MATLAB [Y, M, D, h, m, s.fraction] -> datetime naïf (heure locale du labo)."""
    y, mo, d, h, mi, s = (float(x) for x in np.ravel(vec))
    return datetime(int(y), int(mo), int(d), int(h), int(mi)) + timedelta(seconds=s)


def _first(x):
    a = np.ravel(np.asarray(x))
    return a[0] if a.size else None


def _scalar(x) -> float | None:
    """Partie réelle du premier élément d'un champ scalaire ; None si vide ou NaN."""
    v = _first(x)
    if v is None:
        return None
    v = float(np.real(v))
    return None if np.isnan(v) else v


def _scalar_imag(x) -> float | None:
    """Partie imaginaire du premier élément ; None si le champ est réel, vide ou si elle est nulle."""
    v = _first(x)
    if v is None:
        return None
    im = float(np.imag(v))
    return im if im != 0 and not np.isnan(im) else None


def _agg(fn, x) -> float | None:
    a = np.ravel(np.asarray(x, dtype=float))
    a = a[~np.isnan(a)]
    return float(fn(a)) if a.size else None


def read_cell(path: Path) -> tuple[str, list[dict]]:
    """Retourne (cell_id, liste des cycles) d'un fichier B00xx.mat."""
    cell_id = path.stem
    mat = loadmat(path, simplify_cells=True)
    if cell_id not in mat:
        raise ValueError(f"{path.name}: variable '{cell_id}' absente (clés: {[k for k in mat if not k.startswith('__')]})")
    cycles = mat[cell_id]["cycle"]
    if isinstance(cycles, dict):  # un seul cycle : scipy ne renvoie pas de liste
        cycles = [cycles]
    return cell_id, list(cycles)


def summarize_cycle(cycle_idx: int, cycle: dict) -> dict:
    """Une ligne de raw.nasa_cycles (sans cell_id/source_sha256/run_id)."""
    ctype = cycle["type"]
    if ctype not in CYCLE_TYPES:
        raise ValueError(f"cycle {cycle_idx}: type inconnu {ctype!r}")
    d = cycle["data"]
    row = {
        "cycle_idx": cycle_idx,
        "cycle_type": ctype,
        "ambient_temp_c": _scalar(cycle["ambient_temperature"]),
        "start_time": datevec_to_datetime(cycle["time"]),
        "n_samples": None, "duration_s": None, "capacity_ah": None,
        "v_min": None, "v_max": None, "i_min": None, "i_max": None, "i_median": None,
        "t_min": None, "t_max": None, "t_mean": None, "re_ohm": None, "rct_ohm": None,
        "re_imag_ohm": None, "rct_imag_ohm": None,
    }
    if ctype == "impedance":
        row["n_samples"] = int(np.size(d["Battery_impedance"]))
        row["re_ohm"] = _scalar(d["Re"])
        row["rct_ohm"] = _scalar(d["Rct"])
        row["re_imag_ohm"] = _scalar_imag(d["Re"])
        row["rct_imag_ohm"] = _scalar_imag(d["Rct"])
        return row

    row["n_samples"] = int(np.size(d["Time"]))
    row["duration_s"] = _agg(np.max, d["Time"])
    row["v_min"] = _agg(np.min, d["Voltage_measured"])
    row["v_max"] = _agg(np.max, d["Voltage_measured"])
    row["i_min"] = _agg(np.min, d["Current_measured"])
    row["i_max"] = _agg(np.max, d["Current_measured"])
    row["i_median"] = _agg(np.median, d["Current_measured"])
    row["t_min"] = _agg(np.min, d["Temperature_measured"])
    row["t_max"] = _agg(np.max, d["Temperature_measured"])
    row["t_mean"] = _agg(np.mean, d["Temperature_measured"])
    if ctype == "discharge":
        row["capacity_ah"] = _scalar(d["Capacity"])
    return row


def discharge_samples(cycle_idx: int, cycle: dict) -> Iterator[tuple]:
    """Lignes de raw.nasa_discharge_samples pour un cycle de décharge."""
    d = cycle["data"]
    cols = [
        np.ravel(np.asarray(d[k], dtype=float)).tolist()
        for k in ("Time", "Voltage_measured", "Current_measured",
                  "Temperature_measured", "Current_load", "Voltage_load")
    ]
    if len({len(c) for c in cols}) != 1:
        raise ValueError(f"cycle {cycle_idx}: séries de longueurs différentes {[len(c) for c in cols]}")
    for i, values in enumerate(zip(*cols)):
        yield (cycle_idx, i, *(None if isnan(v) else v for v in values))

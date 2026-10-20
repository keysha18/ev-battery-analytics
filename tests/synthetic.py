"""Cycles NASA synthétiques, même structure que les vrais .mat (champs relevés dans B0005/B0052)."""

from pathlib import Path

import numpy as np
from scipy.io import savemat


def charge(temp=24.0):
    n = 5
    return {
        "type": "charge", "ambient_temperature": temp, "time": np.array([2008, 4, 2, 13, 8, 17.921]),
        "data": {
            "Voltage_measured": np.linspace(3.5, 4.2, n), "Current_measured": np.full(n, -1.5),
            "Temperature_measured": np.linspace(24.0, 26.0, n), "Current_charge": np.full(n, 1.5),
            "Voltage_charge": np.linspace(3.5, 4.2, n), "Time": np.arange(n) * 10.0,
        },
    }


def discharge(capacity=1.8, temp=24.0):
    n = 4
    return {
        "type": "discharge", "ambient_temperature": temp, "time": np.array([2008, 4, 2, 15, 25, 41.593]),
        "data": {
            "Voltage_measured": np.array([4.2, 3.9, 3.4, 2.7]), "Current_measured": np.full(n, -2.0),
            "Temperature_measured": np.array([24.0, 25.0, 26.0, 27.0]),
            "Current_load": np.full(n, 2.0), "Voltage_load": np.array([4.2, 3.9, 3.4, 2.7]),
            "Time": np.arange(n) * 100.0,
            "Capacity": np.array(capacity) if capacity is not None else np.array([]),  # vide comme B0052
        },
    }


def impedance(complex_re_rct=False):
    n = 3
    z = np.array([0.1 + 0.2j] * n)
    re, rct = (np.array(0.0499 - 0.0293j), np.array(0.0499 + 0.0293j)) if complex_re_rct else (
        np.array(0.0446), np.array(0.0694))  # complexes comme dans B0049/B0051
    return {
        "type": "impedance", "ambient_temperature": 24.0, "time": np.array([2008, 4, 18, 20, 55, 29.859]),
        "data": {
            "Sense_current": z, "Battery_current": z, "Current_ratio": z, "Battery_impedance": z,
            "Rectified_Impedance": z, "Re": re, "Rct": rct,
        },
    }


def make_cycles(capacity=1.8):
    return [charge(), discharge(capacity), impedance(), discharge(None)]


def write_mat(path: Path, cell_id: str, cycles: list[dict]) -> Path:
    """Écrit un .mat avec la même forme que NASA : <cell_id>.cycle = tableau 1xN de structs."""
    dt = np.dtype([("type", "O"), ("ambient_temperature", "O"), ("time", "O"), ("data", "O")])
    arr = np.empty((1, len(cycles)), dtype=dt)
    for i, c in enumerate(cycles):
        arr[0, i] = (c["type"], c["ambient_temperature"], c["time"], c["data"])
    path.parent.mkdir(parents=True, exist_ok=True)
    savemat(path, {cell_id: {"cycle": arr}})
    return path

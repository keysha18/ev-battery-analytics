"""Prévision de la fin de vie par extrapolation linéaire, et son backtest."""

from dataclasses import dataclass

import numpy as np
from scipy import stats


@dataclass(frozen=True)
class EolForecast:
    eol_x: float  # indice d'âge prévu où la capacité atteint le seuil
    low: float  # borne basse (pente la plus raide de l'intervalle de confiance)
    high: float | None  # borne haute ; None si l'intervalle de pente inclut 0 (fin de vie non bornée)
    slope: float
    n: int


def forecast_eol(x, y, threshold: float, confidence: float = 0.95, min_points: int = 5) -> EolForecast | None:
    """Droite des moindres carrés de y sur x, extrapolée jusqu'au seuil.

    L'intervalle ne tient compte que de l'incertitude sur la pente (autour du centre des données) :
    il ignore le bruit autour de la droite et surtout l'erreur de modèle (une perte qui s'accélère
    n'est pas linéaire). Il est donc trop étroit et ne vaut que comme ordre de grandeur.
    Retourne None s'il y a trop peu de points ou si la capacité ne décroît pas.
    """
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    n = len(x)
    if n < min_points:
        return None
    res = stats.linregress(x, y)
    if res.slope >= 0:
        return None
    xbar, ybar = float(x.mean()), float(y.mean())
    t = stats.t.ppf(0.5 + confidence / 2, n - 2)
    steep = res.slope - t * res.stderr
    flat = res.slope + t * res.stderr

    def cross(slope: float) -> float:
        return xbar + (threshold - ybar) / slope

    return EolForecast(
        eol_x=cross(res.slope),
        low=cross(steep),
        high=cross(flat) if flat < 0 else None,
        slope=float(res.slope),
        n=n,
    )


@dataclass(frozen=True)
class BacktestRow:
    fraction: float
    cutoff_x: float
    predicted: float
    actual: float
    low: float
    high: float | None

    @property
    def error(self) -> float:
        return self.predicted - self.actual

    @property
    def covered(self) -> bool:
        return self.low <= self.actual and (self.high is None or self.actual <= self.high)


def backtest(x, y, actual_eol_x: float, threshold: float, fractions=(0.5, 0.7, 0.9),
             min_points: int = 10) -> list[BacktestRow]:
    """Rejoue la prévision comme si on n'avait observé que la fraction f de la vie (du premier point
    jusqu'à la vraie fin de vie), puis compare la fin de vie prévue à la vraie."""
    x = np.asarray(x, dtype=float)
    y = np.asarray(y, dtype=float)
    rows = []
    for f in fractions:
        cutoff = x[0] + f * (actual_eol_x - x[0])
        keep = x <= cutoff
        if keep.sum() < min_points:
            continue
        fc = forecast_eol(x[keep], y[keep], threshold)
        if fc is None:
            continue
        rows.append(BacktestRow(f, float(cutoff), fc.eol_x, float(actual_eol_x), fc.low, fc.high))
    return rows
